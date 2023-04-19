#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import sys
from argparse import FileType
from tempfile import NamedTemporaryFile

import yaml

from revng.cli.commands_registry import Command, CommandsRegistry, Options
from revng.cli.revng import run_revng_command


class HardPurgeCommand(Command):
    def __init__(self):
        super().__init__(
            ("model", "hard-purge"),
            "Purge all the functions from original model that does not exist in "
            "the reference model.",
        )

    def register_arguments(self, parser):
        parser.add_argument(
            "reference_model_path", type=FileType("rb"), help="The reference model in form of YAML."
        )
        parser.add_argument(
            "original_model_path",
            type=FileType("r"),
            default=sys.stdin,
            nargs="?",
            help="The original model in form of YAML.",
        )
        parser.add_argument(
            "-o",
            dest="purged_model_path",
            nargs="?",
            default="/dev/stdout",
            help="The pruned model in form of YAML.",
        )

    def log(self, message):
        if self.verbose:
            sys.stderr.write(message + "\n")

    def run(self, options: Options):
        args = options.parsed_args
        self.verbose = args.verbose

        functions_to_preserve = set()

        # Collect functions to be preserved.
        with args.reference_model_path as reference_model_file:
            self.log("Loading the reference model...")
            reference_model = yaml.load(reference_model_file, Loader=yaml.SafeLoader)

            if "Functions" in reference_model:
                for function in reference_model["Functions"]:
                    function_name = function["OriginalName"]
                    self.log(" Function to be preserved: " + function_name)
                    functions_to_preserve.add(function_name)

            if "ImportedDynamicFunctions" in reference_model:
                for dynamic_function in reference_model["ImportedDynamicFunctions"]:
                    function_name = dynamic_function["OriginalName"]
                    self.log(" Dynamic function to be preserved: " + function_name)
                    functions_to_preserve.add(function_name)

        # Remove the functions.
        self.log("Removing functions from original mode...")
        patched_model = {}
        with args.original_model_path as patched_file:
            patched_model = yaml.load(patched_file, Loader=yaml.SafeLoader)

            # Delete functions.
            patched_model["Functions"] = [
                f for f in patched_model["Functions"] if f["OriginalName"] in functions_to_preserve
            ]

            # Delete dynamic functions.
            patched_model["ImportedDynamicFunctions"] = [
                f
                for f in patched_model["ImportedDynamicFunctions"]
                if f["OriginalName"] in functions_to_preserve
            ]

        def temporary_file(suffix="", mode="w+"):
            return NamedTemporaryFile(
                prefix="revng-hard-purge-",
                suffix=suffix,
                mode=mode,
                delete=not options.keep_temporaries,
            )

        with temporary_file(suffix=".yml") as model_file:
            model_file.write("---\n")
            yaml.dump(patched_model, stream=model_file)
            model_file.write("...\n")
            model_file.flush()

            # Optimize the model by purging all unreachable types from any Function.
            result = run_revng_command(
                [
                    "model",
                    "opt",
                    "-prune-unused-types",
                    model_file.name,
                    "-o",
                    args.purged_model_path,
                ],
                options,
            )

            return result

        return 0


def setup(commands_registry: CommandsRegistry):
    commands_registry.register_command(HardPurgeCommand())
