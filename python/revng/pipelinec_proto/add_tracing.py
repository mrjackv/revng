#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

# This scripts injects tracing into one or many C/CPP files. This is done,
# relatively to the output directory provived, by:
# 1. Going through the functions declared in the proto file and creating a
#    wrapper function in TracingWrapper.cpp
# 2. Creating a TracingPrototypes.h file that declares all function prototypes
#    with a '_' (underscore) in front of the name
# 3. For each input file provided, a new one will be created with the same
#    name where the function definition will have the name replaced. Moreover
#    #include will be added to TracingPrototypes.h to restore consistency

import argparse
import re
from pathlib import Path
from typing import List

import jinja2
import yaml

from .proto import Argument, Function, PipelineCProto, ReturnType

SCRIPT_DIR = Path(__file__).parent


def under_functions(text, functions: List[Function]):
    new_text = text[:]
    for function in functions:
        target = re.search(function.name + r"\([^\)]*\)\s*{", new_text, re.DOTALL | re.MULTILINE)
        assert target, f"Target {function.name} not found"
        new_text = new_text[: target.start()] + "_" + new_text[target.start() :]
    return new_text


def inject_trace_header(text: str):
    lines = text.splitlines()
    lines[lines.index("")] = '#include "TracingPrototypes.h"'
    return "".join(f"{line}\n" for line in lines)


def print_arguments(args, call=False):
    if call:
        return ", ".join(arg.name for arg in args)
    else:
        arguments = []
        for arg in args:
            if arg.type_.endswith("[]"):
                arguments.append(f"{arg.type_[:-2]} {arg.name}[]")
            else:
                arguments.append(f"{arg.type_} {arg.name}")
        return ", ".join(arguments)


def gen_trace_variable(proto: PipelineCProto):
    possible_pointers = set()
    for type_ in proto.opaque_pointers:
        possible_pointers.add(f"{type_} *")
        possible_pointers.add(f"const {type_} *")

    def trace_variable(arg: Argument | ReturnType, function: Function):
        name = arg.name if isinstance(arg, Argument) else "ret"

        # Output the the printer for integral types
        if arg.type_ in {"uint8_t", "uint32_t", "uint64_t"}:
            return f"printInt({name})"

        if arg.type_ == "bool":
            return f"printBool({name})"

        # Check if we have a length hint for the current argument
        length_hint = None
        if function.name in proto.length_hints and name in proto.length_hints[function.name]:
            length_hint = proto.length_hints[function.name][name]

        # If we do have a length hint, it means that the argument is either:
        # * A list of {char *, int, void *} handle it accordingly
        # * A buffer denoted by `char *` (e.g. container_deserialize), in this
        #   case we use the printBuffer call that wraps the contents in b64
        if length_hint is not None:
            if arg.type_ in {"char *[]", "const char *[]"}:
                method = "printStringList"
            elif arg.type_ == "const char *":
                method = "printBuffer"
            elif arg.type_ in {"uint8_t []", "uint32_t []", "uint64_t []"}:
                method = "printIntList"
            else:
                method = "printPtrList"
            return f"{method}({name}, {length_hint})"

        # The argument is a 0-terminated string
        if arg.type_ in {"char *", "const char *"}:
            if isinstance(arg, Argument):
                # Special case the _destroy methods, those always want
                # the pointer
                if function.name.endswith("_destroy"):
                    return f"printOpaquePtr({name})"
                else:
                    # Print as a normal string literal
                    return f"printString({name})"
            else:
                # For returned strings we always want the pointer
                return f"printOpaquePtr({name})"

        # Lastly, handle opaque pointers native to PipelineC
        if arg.type_ in possible_pointers:
            return f"printOpaquePtr({name})"

        raise ValueError(f"Don't know how to trace {arg}")

    return trace_variable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--proto", type=str, required=True, help="Prototypes json file")
    parser.add_argument("-t", "--tracing", type=str, action="append", help="Tracing cpp files")
    parser.add_argument("-i", "--input", type=str, action="append", help="Input cpp source files")
    parser.add_argument("output", type=str, help="Output directory")

    args = parser.parse_args()
    if len(args.tracing) == 0:
        raise ValueError("At least one tracing file is required")

    if len(args.input) == 0:
        raise ValueError("At least one input file is required")

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(SCRIPT_DIR))
    template = env.get_template("tracing_wrapper.cpp.j2")
    with open(args.proto) as proto_file:
        proto = PipelineCProto.from_dict(yaml.safe_load(proto_file))

    output = Path(args.output)
    inputs: List[Path] = [Path(input_) for input_ in args.input]

    with open(output / "TracingPrototypes.h", "w") as output_file:
        output_file.write("#pragma once\n")
        output_file.write('#include "revng/PipelineC/PipelineC.h"\n')
        for f in proto.functions:
            output_file.write(f"{f.return_type.type_} _{f.name}({print_arguments(f.arguments)});\n")

    with open(output / "TracingWrapper.cpp", "w") as output_file:
        for trace_file in args.tracing:
            output_file.write(Path(trace_file).read_text() + "\n")
        output_file.write(
            template.render(
                functions=proto.functions,
                print_arguments=print_arguments,
                trace_variable=gen_trace_variable(proto),
            )
        )

    for input_ in inputs:
        function_replaced = under_functions(input_.read_text(), proto.functions)
        header_inserted = inject_trace_header(function_replaced)
        with open(output / input_.name, "w") as output_file:
            output_file.write(header_inserted)


if __name__ == "__main__":
    main()
