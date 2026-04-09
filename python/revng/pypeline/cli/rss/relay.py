#
# This file is distributed under the MIT License. See LICENSE.md for details.
#


import click
import uvicorn

import revng.pypeline.rss_server.relay as app
from revng.pypeline.cli.uvicorn import add_uvicorn_clopts, patch_uvicorn_server_exit


@click.command(help="Start the notification relay HTTP server")
@add_uvicorn_clopts
@click.option("--psk", help="The pre-shared key for the /publish endpoint")
def relay(production: bool, psk: str, **kwargs):
    if not production:
        kwargs.setdefault("host", "127.0.0.1")
    else:
        kwargs.setdefault("host", "0.0.0.0")

    patch_uvicorn_server_exit(lambda: app.shutdown_begun)
    # Start the uvicorn server
    uvicorn.run(app=app.make_starlette(psk), **kwargs)
