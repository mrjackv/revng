#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from pathlib import Path

from revng.cli.commands_registry import Command, CommandsRegistry, Options
from revng.cli.support import collect_files, get_root, log_error
from revng.pipelinec_proto.compile import compile_trace


class CompileTraceCommand(Command):
    def __init__(self):
        super().__init__(("compile-trace",), "Compile a revng trace file")

    def register_arguments(self, parser):
        parser.add_argument("-p", "--proto", type=str, help="Prototypes json file")
        parser.add_argument("-c", "--c-file", type=str, help="Output C file")
        parser.add_argument("-o", "--executable", type=str, help="Output Executable trace executor")
        parser.add_argument("trace_file", type=str, help="Trace file")

    def run(self, options: Options) -> int:
        args = options.parsed_args
        if args.proto is None:
            sp = options.search_prefixes
            proto_candidates = collect_files(sp, ["share", "revng"], "pipelinec_proto.yml")
            assert len(proto_candidates) == 1
            proto = Path(proto_candidates[0])
        else:
            proto = Path(args.proto)

        if args.c_file is None and args.executable is None:
            log_error("Either one of --c-file and --executable needs to be specified")
            return 1

        c_file = Path(args.c_file) if args.c_file is not None else None
        executable = Path(args.executable) if args.executable is not None else None
        compile_trace(Path(args.trace_file), proto, get_root(), c_file, executable)
        return 0


def setup(commands_registry: CommandsRegistry):
    commands_registry.register_command(CompileTraceCommand())
