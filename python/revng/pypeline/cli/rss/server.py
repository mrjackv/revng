#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import os
from importlib import import_module

import click
import uvicorn

from revng.pypeline.cli.uvicorn import add_uvicorn_clopts
from revng.pypeline.rss_server.server import RSSHTTPServer
from revng.pypeline.rss_server.storage import RSSStorage


@click.command(help="Start the Remote Storage Server HTTP server")
@add_uvicorn_clopts
@click.option(
    "-t",
    "--storage-type",
    default="revng.pypeline.rss_server.postgres:PostgresRSSStorage",
    help="The fully-qualified class that will be used as the storage backend",
    show_default=True,
)
@click.option(
    "-c",
    "--connection-string",
    default="postgresql://localhost/rss",
    help="The connection string that will be used by the storage class",
    show_default=True,
)
@click.option("--notification-url", help="URL to send notifications to")
@click.option("--notification-psk", help="PSK to use when sending notifications")
@click.option(
    "--public-notification-url",
    help="public-facing URL in case the notification url is private",
)
def server(
    production: bool,
    storage_type: str,
    connection_string: str,
    notification_url: str | None,
    notification_psk: str | None,
    public_notification_url: str | None,
    **kwargs
):
    if not production:
        os.environ["STARLETTE_DEBUG"] = "1"
        os.environ["REVNG_ORIGINS"] = "*"
        kwargs.setdefault("host", "127.0.0.1")
    else:
        kwargs.setdefault("host", "0.0.0.0")

    # Import the storage class
    module_path, class_name = storage_type.rsplit(":", 1)
    storage_class: type[RSSStorage] = getattr(import_module(module_path), class_name)

    # Create the server instance
    server = RSSHTTPServer(
        storage_class,
        connection_string,
        notification_url,
        notification_psk,
        public_notification_url,
    )

    # Start the uvicorn server
    uvicorn.run(app=server.make_starlette(), **kwargs)
