#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import asyncio
from asyncio import Queue
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import override

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute

from revng.pypeline.storage.notification_queue import MultiQueue
from revng.pypeline.storage.storage_provider import ProjectID
from revng.pypeline.utils.notification_broker import NotificationBroker, NotificationSubscriber
from revng.pypeline.utils.notification_broker import Stream
from revng.pypeline.utils.starlette import NotificationWebsocket, get_project_id

shutdown_begun: asyncio.Event | None = None
QUEUES: dict[ProjectID, MultiQueue[bytes]] = defaultdict(MultiQueue)


class MultiNotifiactionBroker(NotificationBroker):
    @override
    async def subscribe(
        self, project_id: ProjectID | None, stream: Stream
    ) -> NotificationSubscriber:
        assert project_id is not None, "project_id = None is unsupported"
        return await super().subscribe(project_id, stream)

    @override
    async def get_queue(self, project_id: ProjectID | None) -> Queue[bytes]:
        assert project_id is not None
        return QUEUES[project_id].get_queue()


def make_starlette(publish_psk: str) -> Starlette:
    notification_broker = MultiNotifiactionBroker()
    ws_notifications = NotificationWebsocket(notification_broker, lambda: shutdown_begun)

    async def status(request):
        return PlainTextResponse("OK")

    async def publish(request: Request):
        project_id = get_project_id(request.headers)
        if project_id is None:
            return PlainTextResponse("Project ID must be supplied", 400)

        authorization = request.headers.get("authorization")
        if authorization != f"Bearer {publish_psk}":
            return PlainTextResponse("Invalid authorization header", 403)

        body = await request.body()
        QUEUES[project_id].send(body)
        return PlainTextResponse("Sent")

    @asynccontextmanager
    async def lifespan(app):
        global shutdown_begun
        shutdown_begun = asyncio.Event()
        yield

    # Create the Starlette application
    return Starlette(
        debug=False,
        routes=[
            Route("/publish", publish, methods=["POST"]),
            WebSocketRoute("/notifications", ws_notifications.endpoint),
            Route("/status", status, methods=["GET"]),
        ],
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            Middleware(GZipMiddleware, minimum_size=1024),
        ],
    )
