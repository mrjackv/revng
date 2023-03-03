#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pycparser.c_ast import FuncDecl, NodeVisitor, PtrDecl, TypeDecl, Typedef
from pycparser.c_generator import CGenerator
from pycparser.c_parser import CParser

# Regex that's used to remove all comments within the source headers
comment_re = re.compile(r"/\*.*?\*/|//([^\n\\]|\\.)*?$", re.DOTALL | re.MULTILINE)
# Regex matching function names in PipelineC
name_re = re.compile("[a-zA-Z0-9_]+$")

# Mapping of Function Name -> Argument -> Length argument
LENGTH_HINTS = {
    "rp_initialize": {
        "argv": "argc",
        "libraries_path": "libraries_count",
        "signals_to_preserve": "signals_to_preserve_count",
    },
    "rp_manager_create": {
        "pipelines_path": "pipelines_count",
        "pipeline_flags": "pipeline_flags_count",
    },
    "rp_manager_create_from_string": {
        "pipelines": "pipelines_count",
        "pipeline_flags": "pipeline_flags_count",
    },
    "rp_manager_produce_targets": {"targets": "targets_count"},
    "rp_manager_run_analysis": {"targets": "targets_count"},
    "rp_target_create": {"path_components": "path_components_count"},
    "rp_manager_container_deserialize": {"content": "size"},
}


@dataclass
class Argument:
    # Name of the argument (e.g. "foo")
    name: str
    # Declaration of the argument (with type, e.g. "int *foo[]")
    decl: str


@dataclass
class Function:
    # Name of the function
    name: str
    # List of arguments
    arguments: List[Argument]
    # Return type
    return_type: str


class Visitor(NodeVisitor):
    def __init__(self):
        super().__init__()
        self.c_gen = CGenerator()
        self.functions: List[Function] = []
        self.types: List[str] = []

    def visit_FuncDecl(self, node: FuncDecl):  # noqa: N802
        name = self.get_name(node)
        return_type = self.c_gen.visit(node.type)
        arguments = []
        if node.args is not None:
            arguments = [self.parse_argument(arg) for arg in node.args.params]
        self.functions.append(Function(name, arguments, return_type))

    def visit_Typedef(self, node: Typedef):  # noqa: N802
        if node.name not in {"bool", "uint8_t", "uint32_t", "uint64_t"}:
            self.types.append(node.name)

    def get_name(self, node: PtrDecl | TypeDecl) -> str:
        if isinstance(node.type, TypeDecl):
            return node.type.declname
        else:
            return node.type.type.declname

    def parse_argument(self, arg: str) -> Argument:
        string: str = self.c_gen.visit(arg)
        name_match = name_re.search(string.removesuffix("[]"))
        assert name_match is not None
        return Argument(name_match[0], string)


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


def parse_headers(headers: List[Path]):
    # Fixup definitions for types not present in C99
    text = """
typedef struct bool bool;
typedef struct uint8_t uint8_t;
typedef struct uint32_t uint32_t;
typedef struct uint64_t uint64_t;
"""
    for header in headers:
        text += header.read_text()

    # Remove comments and pre-processor directives
    text = comment_re.sub("", text)
    text = "".join(ln if not ln.startswith("#") else "\n" for ln in text.splitlines(True))

    parser = CParser()
    visitor = Visitor()
    visitor.visit(parser.parse(text, "input"))
    return (visitor.functions, visitor.types)


def generate(output: Path, tracing: Path, impl_files: List[Path], functions: List[Function]):
    with open(output / "TracingPrototypes.h", "w") as output_file:
        output_file.write("#pragma once\n")
        output_file.write('#include "revng/PipelineC/PipelineC.h"\n\n')
        for f in functions:
            args = ", ".join(a.decl for a in f.arguments)
            output_file.write(f"{f.return_type} _{f.name}({args});\n")

    with open(output / "PipelineCTracing.cpp", "w") as output_file:
        output_file.write(tracing.read_text())
        output_file.write('\n#include "TracingPrototypes.h"\n\n')
        for f in functions:
            args = ", ".join(a.decl for a in f.arguments)
            arg_names = "".join(f", {a.name}" for a in f.arguments)
            if f.name in LENGTH_HINTS:
                for arg, len_arg in LENGTH_HINTS[f.name].items():
                    arg_pos = next(i for i, a in enumerate(f.arguments) if a.name == arg)
                    len_arg_pos = next(i for i, a in enumerate(f.arguments) if a.name == len_arg)
                    output_file.write(
                        f'template<> constexpr int LengthHint<"{f.name}", {arg_pos}> = {len_arg_pos};\n'
                    )
            output_file.write(
                f'{f.return_type} {f.name}({args}) {{ return wrap<"{f.name}">(_{f.name}{arg_names}); }};\n'
            )

    for impl in impl_files:
        functions_replaced = under_functions(impl.read_text(), functions)
        header_inserted = inject_trace_header(functions_replaced)
        with open(output / impl.name, "w") as output_file:
            output_file.write(header_inserted)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--header", type=str, action="append", help="Header file to parse")
    parser.add_argument("-t", "--tracing", type=str, action="append", help="Tracing cpp files")
    parser.add_argument(
        "-m", "--impl-file", type=str, action="append", help="Input cpp source files"
    )
    parser.add_argument("output", type=str, help="Output File")
    args = parser.parse_args()

    if args.header is None or len(args.header) == 0:
        raise ValueError("At least one header must be specified")

    if args.impl_file is None or len(args.impl_file) == 0:
        raise ValueError("At least one implementation file must be specified")

    functions, types = parse_headers([Path(p) for p in args.header])
    generate(Path(args.output), Path(args.tracing[0]), [Path(f) for f in args.impl_file], functions)


if __name__ == "__main__":
    main()
