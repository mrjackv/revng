#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from .commands_registry import Command, Options, commands_registry
from .support import build_command_with_loads, collect_files, interleave, run


class ArtifactCommand(Command):
    def __init__(self):
        super().__init__(("artifact",), "revng artifact producer", False)

    def register_arguments(self, parser):
        pass

    def run(self, options: Options):
        pipelines = collect_files(options.search_prefixes, ["share", "revng", "pipelines"], "*.yml")
        pipelines_args = interleave(pipelines, "-P")
        command = build_command_with_loads(
            "revng-artifact", pipelines_args + options.remaining_args, options
        )
        return run(command, options)


commands_registry.register_command(ArtifactCommand())
