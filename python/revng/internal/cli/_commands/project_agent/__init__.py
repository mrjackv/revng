#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import base64
import json
import re
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Literal, Protocol

import click

from revng.internal.cli.common import CommandRegistry, cli_logger
from revng.internal.support import cache_directory, check_unix_socket
from revng.pypeline.cli.context import ClickContext, pass_context
from revng.pypeline.storage.storage_provider import storage_provider_factory_factory

# Re-run auto-detection when the cached check is older than this
CACHE_MAX_AGE = 24 * 60 * 60  # 24 hours
# OpenAI advertises the plan in this claim, both in codex' and opencode's tokens
OPENAI_AUTH_CLAIM = "https://api.openai.com/auth"
# Plan values that do not count as a subscription
INACTIVE_PLANS = ("", "free")


@dataclass
class Subscription:
    """An active subscription. `expiry` is None for an agent that reports none."""

    expiry: int | None


def _run(command: list[str], ignore_status: bool = False) -> str | None:
    """Run `command`, returning its output, or None if it is missing or fails."""
    if shutil.which(command[0]) is None:
        return None

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0 and not ignore_status:
        return None

    return result.stdout


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _walk_dicts(value: Any, *keys: str) -> Any:
    """Walk nested dictionaries, returning None on any missing or non-dict step."""
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)

    return value


def _jwt_claims(token: Any) -> dict | None:
    """Decode a JWT payload without verifying it: these are our own tokens."""
    if not isinstance(token, str):
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    # JWTs use unpadded base64url
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return None

    return claims if isinstance(claims, dict) else None


def _plan(claims: dict) -> Any:
    """The plan advertised by an OpenAI token, None for any other issuer."""
    return _walk_dicts(claims, OPENAI_AUTH_CLAIM, "chatgpt_plan_type")


def _expiry(claims: dict) -> int | None:
    expiry = claims.get("exp")
    return expiry if isinstance(expiry, int) else None


class Agent(Protocol):
    name: str

    def detect(self) -> int | Literal[True] | None: ...
    def run(self, cwd: Path, prompt: str) -> int: ...


class Claude(Agent):
    name = "claude"

    @staticmethod
    def detect() -> Literal[True] | None:
        """`claude auth status` reports the plan itself and exposes no token."""
        output = _run(["claude", "auth", "status", "--json"])
        if output is None:
            return None

        try:
            status = json.loads(output)
        except ValueError:
            return None

        # An API key is not a subscription
        if not status.get("loggedIn") or status.get("authMethod") != "claude.ai":
            return None

        if status.get("subscriptionType") in (None, *INACTIVE_PLANS):
            return None

        return True

    @staticmethod
    def run(cwd: Path, prompt: str) -> int:
        return subprocess.run(["claude", prompt], cwd=cwd, check=False).returncode


class Codex(Agent):
    name = "codex"

    @staticmethod
    def detect() -> int | None:
        """`codex doctor --json` reports the login mode and the auth file, untruncated."""
        # Unrelated failing checks (e.g. network) must not hide the auth report
        output = _run(["codex", "doctor", "--json"], ignore_status=True)
        if output is None:
            return None

        try:
            report = json.loads(output)
        except ValueError:
            return None

        details = _walk_dicts(report, "checks", "auth.credentials", "details")
        # The alternatives are an API key login or no login at all
        if _walk_dicts(details, "stored auth mode") != "chatgpt":
            return None

        auth_file = _walk_dicts(details, "auth file")
        if not isinstance(auth_file, str):
            return None

        claims = _jwt_claims(_walk_dicts(_read_json(Path(auth_file)), "tokens", "id_token"))
        if claims is None:
            return None

        plan = _plan(claims)
        if plan in (None, *INACTIVE_PLANS):
            return None

        return _expiry(claims)

    @staticmethod
    def run(cwd: Path, prompt: str) -> int:
        return subprocess.run(["codex", prompt], cwd=cwd, check=False).returncode


class Opencode(Agent):
    name = "opencode"

    @staticmethod
    def _detect_opencode() -> int | None:
        """opencode has no notion of a plan, so fall back to its stored credentials."""
        if (output := _run(["opencode", "debug", "paths"])) is None:
            return None

        data_dir_re = re.compile(r"^data\s+(\S+)$")
        for line in output.splitlines():
            if (match := data_dir_re.match(line)) is not None:
                break
        else:
            return None

        credentials = _read_json(Path(match.group(1)) / "auth.json")
        if not isinstance(credentials, dict):
            return None

        for credential in credentials.values():
            if not isinstance(credential, dict) or credential.get("type") != "oauth":
                continue

            claims = _jwt_claims(credential.get("access"))
            # Only OpenAI advertises a plan, take any other provider at face value
            if claims is None or _plan(claims) in INACTIVE_PLANS:
                continue

            return _expiry(claims)

        return None

    @staticmethod
    def run(cwd: Path, prompt: str) -> int:
        return subprocess.run(["opencode", "--prompt", prompt], cwd=cwd, check=False).returncode


AGENTS: list[Agent] = [Claude, Codex, Opencode]  # type: ignore
AGENT_NAMES = (a.name for a in AGENTS)


def _read_cache(cache_file: Path) -> str | None:
    cache = {}
    if cache_file.is_file():
        cache = _read_json(cache_file)

    if cache == {} or cache["agent"] not in AGENT_NAMES:
        return None

    now = time.time()
    if now - cache["check_time"] > CACHE_MAX_AGE or cache["expiry"] <= now:
        return None

    return cache["agent"]


def _detect_agent() -> Agent:
    cache_file = cache_directory() / "agent-subscription.json"
    cached_agent_name = _read_cache(cache_file)
    if cached_agent_name is not None:
        cli_logger.debug_log(f'Using cached agent: "{cached_agent_name}"')
        for agent in AGENTS:
            if agent.name == cached_agent_name:
                return agent

    for agent in AGENTS:
        subscription = agent.detect()
        if subscription is not None:
            payload = {
                "agent": agent,
                "expiry": None if subscription is True else subscription,
                "check-time": int(time.time()),
            }
            cache_file.write_text(json.dumps(payload))
            return agent

    raise click.ClickException(
        f"None of {', '.join(AGENT_NAMES)} has an active subscription. "
        "Use --agent to pick one anyway."
    )


@contextmanager
def _daemon(ctx: ClickContext, socket_path: Path) -> Generator[None]:
    """Start a daemon unless one already answers on `socket_path`, and stop it afterwards."""
    if check_unix_socket(socket_path):
        cli_logger.debug_log(f"Reusing the daemon on {socket_path}")
        yield
        return

    process = subprocess.Popen(["revng", "-C", str(ctx.obj.base_directory), "project", "daemon"])
    try:
        while not check_unix_socket(socket_path):
            if (returncode := process.poll()) is not None:
                raise click.ClickException(f"`revng project daemon` exited with {returncode}")
            time.sleep(0.1)
        yield
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(10.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@click.command(name="agent")
@click.option(
    "--agent",
    type=click.Choice(AGENT_NAMES),
    help="Use the specified agent, skipping subscription auto-detection.",
)
@pass_context
def project_agent(ctx: ClickContext, agent: str | None) -> int:
    """Run a coding agent against the project's daemon."""

    factory = storage_provider_factory_factory(ctx.obj.storage_provider_url)
    model_path = factory.model_path(ctx.obj.base_directory)
    if model_path is None:
        raise click.UsageError("The storage provider does not have a model path, bailing.")

    socket_path = model_path.parent / "revng.sock"
    if agent is not None:
        if shutil.which(agent) is None:
            raise click.ClickException(f"{agent} is not installed")
        agent_class = next((a for a in AGENTS if a.name == agent))
    else:
        agent_class = _detect_agent()

    with _daemon(ctx, socket_path):
        return agent_class.run(ctx.obj.base_directory, "")


def setup(registry: CommandRegistry):
    registry.register(("project",), project_agent)
