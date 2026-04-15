#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from asyncio import Event
from typing import Callable

import click
import uvicorn
from click.decorators import _param_memo
from uvicorn.main import Server


# The ASGI spec does not have any facility to report that the shutdown of the
# server has begun. The lifespan protocol sends the `lifespan.shutdown` message
# only when "the server has stopped accepting connections and closed all active
# connections" (cited from the spec).
# This does not work well with long-running websocket connections, because we
# want to know when the server has started shutting down so that we can close
# the sockets. This create a catch-22 where the sockets are waiting for the
# shutdown signal to be closed and the server is waiting for the sockets to
# close to send the shutdown signal.
# Seemingly [1] the only reliable way of fixing this is to monkey-patch the
# `handle_exit` method of `uvicorn.main.Server` so that we can trigger an
# `asyncio.Event` variable and trigger the websockets to shut down.
# Uvicorn has a pending PR [2] that makes this unnecessary but it hasn't been
# merged yet.
#
# [1] https://stackoverflow.com/q/58133694
# [2] https://github.com/Kludex/uvicorn/pull/2242
def patch_uvicorn_server_exit(event_getter: Callable[[], Event | None]):
    original_handle_exit = Server.handle_exit

    def new_handle_exit(self, *args, **kwargs):
        if not self.should_exit:
            event = event_getter()
            assert event is not None
            event.set()
        return original_handle_exit(self, *args, **kwargs)

    Server.handle_exit = new_handle_exit  # type: ignore[method-assign]


# End of hack to trigger websocket shutdown


def add_uvicorn_clopts(command):
    def is_param_disallowed(name: str):
        return name in ("app", "reload", "version", "factory", "app_dir") or name.startswith(
            "reload_"
        )

    # Inherit all params from the uvicorn cli
    for param in uvicorn.main.params:
        if param.name is not None and is_param_disallowed(param.name):
            continue

        # Add help text that explains production changes
        if param.name == "host":
            param.default = None  # type: ignore [attr-defined]
            param.show_default = False  # type: ignore [attr-defined]
            help_addition = " Defaults to 0.0.0.0 in production and 127.0.0.1 otherwise."
            if not param.help.endswith(help_addition):  # type: ignore[attr-defined]
                param.help += help_addition  # type: ignore [attr-defined]

        _param_memo(command, param)

    # Add the --production flag
    click.option(
        "--production",
        is_flag=True,
        help="Enable production settings.",
    )(command)

    return command
