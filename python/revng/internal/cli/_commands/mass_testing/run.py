#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import argparse
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from revng.internal.cli.support import run
from revng.internal.support.collect import collect_files

from ...commands_registry import Command, Options


class MassTestingRunCommand(Command):
    def __init__(self):
        super().__init__(("mass-testing", "run"), "Run a mass-testing configuration")

    def register_arguments(self, parser: argparse.ArgumentParser):
        parser.description = "Run a mass-testing configuration"
        parser.add_argument("build_dir", help="Build directory")

    def run(self, options: Options):
        args = options.parsed_args

        meta_file = Path(args.build_dir) / "meta.yml"
        if meta_file.exists():
            with open(meta_file) as f:
                meta_data = yaml.safe_load(f)
        else:
            meta_data = {}

        if "cpu_count" not in meta_data:
            meta_data["cpu_count"] = len(os.sched_getaffinity(0))
        if "start_time" not in meta_data:
            meta_data["start_time"] = time.time()
        with open(meta_file, "w") as f:
            yaml.safe_dump(meta_data, f)

        bin_dir = TemporaryDirectory(prefix="revng-mass-testing-bin-")
        prefix = "revng-"
        for executable in collect_files(
            options.search_prefixes, ["libexec", "revng", "mass-testing"], f"{prefix}*"
        ):
            os.symlink(
                executable,
                os.path.join(bin_dir.name, os.path.basename(executable).removeprefix(prefix)),
            )

        new_env = os.environ.copy()
        new_env["PATH"] = f"{bin_dir.name}:{new_env['PATH']}"

        run(["ninja", "-k0", "-C", args.build_dir], options, new_env)
