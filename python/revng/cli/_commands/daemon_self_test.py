#!/usr/bin/env python3
#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import asyncio
import json
import os
import sys
from argparse import ArgumentParser
from graphlib import TopologicalSorter
from subprocess import PIPE, STDOUT, Popen
from tempfile import TemporaryDirectory
from typing import Tuple

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from revng.cli.commands_registry import Command, CommandsRegistry, Options


class DaemonSelfTestCommand(Command):
    FILTER_ENV = [
        "STARLETTE_DEBUG",
        "REVNG_NOTIFY_FIFOS",
        "REVNG_ORIGINS",
        "REVNG_DATA_DIR",
        "REVNG_PROJECT_ID",
    ]

    def __init__(self):
        super().__init__(
            ("daemon-self-test",),
            "Check if revng-daemon can produce all artifacts given an executable",
        )

    def register_arguments(self, parser: ArgumentParser):
        parser.add_argument(
            "-e",
            "--external",
            help="Use the specified external address instead of using the local daemon",
        )
        parser.add_argument(
            "executable", metavar="EXECUTABLE", help="Executable to run the test with"
        )

    def run(self, options: Options):
        if options.parsed_args.external is not None:
            self.url = options.parsed_args.external
            self.process = None
        else:
            temp_folder = TemporaryDirectory()
            self.url = f"unix:{temp_folder.name}/daemon.sock"
            self.process = Popen(
                ["revng", "daemon", "-b", self.url],
                env={k: v for k, v in os.environ.items() if k not in self.FILTER_ENV},
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )

        self.log(f"Starting daemon self-test, url: {self.url}")
        executable_path = options.parsed_args.executable
        assert os.path.isfile(executable_path)
        try:
            asyncio.run(self.run_self_test(executable_path))
        except Exception as e:
            self.fail(e)

        if self.process is not None:
            self.process.terminate()
            return_code = self.process.wait()
            if return_code != 0:
                self.fail(RuntimeError(f"Daemon exited with code {return_code}"))

    @staticmethod
    def log(string: str):
        sys.stderr.write(f"{string}\n")
        sys.stderr.flush()

    def fail(self, ex: Exception):
        if self.process is not None:
            self.process.terminate()
            self.process.communicate()
            if self.process.stdout is not None:
                self.log(f"\n\n Daemon Stacktrace:\n{self.process.stdout.read()}")
        raise ex

    async def get_connection(self) -> Tuple[aiohttp.BaseConnector, str]:
        if self.url.startswith("unix:"):
            return (aiohttp.UnixConnector(self.url.replace("unix:", "", 1)), "dummy")
        else:
            return (aiohttp.TCPConnector(), self.url)

    async def run_self_test(self, executable_path: str):
        try:
            await self.check_server_up()
        except ValueError as e:
            self.fail(e)

        connector, address = await self.get_connection()
        transport = AIOHTTPTransport(
            f"http://{address}/graphql/", client_session_args={"connector": connector, "timeout": ClientTimeout()}
        )
        async with Client(
            transport=transport, fetch_schema_from_transport=True, execute_timeout=None
        ) as client:
            upload_q = gql(
                """
                mutation upload($file: Upload!) {
                    uploadFile(file: $file, container: "input")
                }"""
            )

            with open(executable_path, "rb") as binary_file:
                await client.execute(
                    upload_q, variable_values={"file": binary_file}, upload_files=True
                )
            self.log("Upload complete")

            await client.execute(gql("mutation { runAllAnalyses }"))
            self.log("Autoanalysis complete")

            q = gql(
                """{ info { steps {
                    name
                    parent
                    artifacts {
                        kind { name }
                        container { name }
                    }
                }}}"""
            )

            result = await client.execute(q)

            steps = {step["name"]: step for step in result["info"]["steps"]}
            topo_sorter: TopologicalSorter = TopologicalSorter()
            for step in steps.values():
                if step["parent"] is not None:
                    topo_sorter.add(step["name"], step["parent"])

            for step_name in topo_sorter.static_order():
                step = steps[step_name]
                if step["artifacts"] is None:
                    continue

                artifacts_container = step["artifacts"]["container"]["name"]
                artifacts_kind = step["artifacts"]["kind"]["name"]

                q = gql(
                    """
                query cq($step: String!, $container: String!) {
                    container(name: $container, step: $step) {
                        targets { serialized }
                    }
                }"""
                )
                arguments = {"step": step_name, "container": artifacts_container}
                res = await client.execute(q, arguments)

                target_list = {
                    target["serialized"]
                    for target in res["container"]["targets"]
                    if target["serialized"].endswith(f":{artifacts_kind}")
                }
                targets = ",".join(target_list)

                self.log(f"Producing {step_name}/{artifacts_container}/*:{artifacts_kind}")
                q = gql(
                    """
                query($step: String!, $container: String!, $target: String!) {
                    produce(step: $step, container: $container, targetList: $target)
                }"""
                )
                result = await client.execute(q, {**arguments, "target": targets})
                json_result = json.loads(result["produce"])
                assert target_list == set(json_result.keys()), "Some targets were not produced"

    async def check_server_up(self):
        connector, address = await self.get_connection()
        session = ClientSession(connector=connector, timeout=ClientTimeout(total=2.0))
        for _ in range(10):
            try:
                async with session.get(f"http://{address}/status") as req:
                    if req.status == 200:
                        connector.close()
                        return
                    await asyncio.sleep(1.0)
            except aiohttp.ClientConnectionError:
                await asyncio.sleep(1.0)
        connector.close()
        raise ValueError()


def setup(commands_registry: CommandsRegistry):
    commands_registry.register_command(DaemonSelfTestCommand())
