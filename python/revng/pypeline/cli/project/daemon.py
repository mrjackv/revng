#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import os

import click
import uvicorn

import revng.pypeline.daemon.app as app
from revng.pypeline.cli.context import ClickContext, pass_context
from revng.pypeline.cli.utils import PypeCommand
from revng.pypeline.cli.uvicorn import add_uvicorn_clopts, patch_uvicorn_server_exit
from revng.pypeline.daemon.daemon import Daemon


@click.command(cls=PypeCommand)
@add_uvicorn_clopts
@pass_context
def run_daemon(ctx: ClickContext, production, **kwargs):
    """Start the HTTP daemon."""

    # Configure uvicorn logging
    log_config = uvicorn.config.LOGGING_CONFIG

    # Setup formatting
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["access"]["fmt"] = log_format
    log_config["formatters"]["default"]["fmt"] = log_format

    for uvlogger in log_config["loggers"].values():
        uvlogger["level"] = "INFO"

    if not production:
        os.environ["STARLETTE_DEBUG"] = "1"
        os.environ["REVNG_ORIGINS"] = "*"
        kwargs.setdefault("host", "127.0.0.1")
    else:
        kwargs.setdefault("host", "0.0.0.0")

    daemon = Daemon(
        pipeline=ctx.obj.pipeline,
        storage_provider_url=ctx.obj.storage_provider_url,
        cache_dir=ctx.obj.cache_dir,
        base_directory=ctx.obj.base_directory,
    )
    patch_uvicorn_server_exit(lambda: app.shutdown_begun)

    # Start the uvicorn server
    uvicorn.run(app=app.make_starlette(daemon), **kwargs)
