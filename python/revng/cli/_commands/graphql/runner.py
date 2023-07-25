#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import asyncio
import json
import sys
from graphlib import TopologicalSorter
from typing import Awaitable, Callable, Iterable, List, Tuple

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from gql import Client, gql
from gql.client import AsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport

from .daemon_handler import DaemonHandler

Runner = Callable[[AsyncClientSession], Awaitable[None]]


async def run_on_daemon(handler: DaemonHandler, runners: Iterable[Runner]):
    await handler.wait_for_start()
    await check_server_up(handler.url)

    connector, address = get_connection(handler.url)
    transport = AIOHTTPTransport(
        f"http://{address}/graphql/",
        client_session_args={"connector": connector, "timeout": ClientTimeout()},
    )
    async with Client(
        transport=transport, fetch_schema_from_transport=True, execute_timeout=None
    ) as client:
        for runner in runners:
            await runner(client)


def upload_file(executable_path: str):
    async def runner(client: AsyncClientSession):
        upload_q = gql(
            """
            mutation upload($file: Upload!) {
                uploadFile(file: $file, container: "input")
            }"""
        )

        with open(executable_path, "rb") as binary_file:
            await client.execute(upload_q, variable_values={"file": binary_file}, upload_files=True)
        log("Upload complete")

    return runner


def run_analyses_lists(analyses_lists: List[str]):
    async def runner(client: AsyncClientSession):
        lists_q = gql("""{ info { analysesLists { name }}}""")
        available_analyses_lists = await client.execute(lists_q)
        list_names = [al["name"] for al in available_analyses_lists["info"]["analysesLists"]]

        for list_name in analyses_lists:
            assert list_name in list_names, f"Missing analyses list {list_name}"
            await client.execute(gql(f'mutation {{ runAnalysesList(name: "{list_name}") }}'))

        log("Autoanalysis complete")

    return runner


def produce_artifacts(filter_: List[str] | None = None):
    async def runner(client: AsyncClientSession):
        q = gql(
            """{ info { steps {
                name
                component
                parent
                artifacts {
                    kind { name }
                    container { name }
                }
            }}}"""
        )

        result = await client.execute(q)

        if filter_ is None:
            filtered_steps = list(result["info"]["steps"])
        else:
            filtered_steps = [
                step
                for step in result["info"]["steps"]
                if step["component"] in filter_ or step["name"] == "begin"
            ]

        steps = {step["name"]: step for step in filtered_steps}
        topo_sorter: TopologicalSorter = TopologicalSorter()
        for step in steps.values():
            if step["parent"] is not None:
                if step["parent"] in steps:
                    topo_sorter.add(step["name"], step["parent"])
                else:
                    topo_sorter.add(step["name"], "begin")

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

            log(f"Producing {step_name}/{artifacts_container}/*:{artifacts_kind}")
            q = gql(
                """
            query($step: String!, $container: String!, $target: String!) {
                produce(step: $step, container: $container, targetList: $target)
            }"""
            )
            result = await client.execute(q, {**arguments, "target": targets})
            json_result = json.loads(result["produce"])
            assert target_list == set(json_result.keys()), "Some targets were not produced"

    return runner


async def check_server_up(url: str):
    connector, address = get_connection(url)
    session = ClientSession(connector=connector, timeout=ClientTimeout())
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


def get_connection(url) -> Tuple[aiohttp.BaseConnector, str]:
    if url.startswith("unix:"):
        return (aiohttp.UnixConnector(url.replace("unix:", "", 1)), "dummy")
    return (aiohttp.TCPConnector(), url)


def log(string: str):
    sys.stderr.write(f"{string}\n")
    sys.stderr.flush()
