#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import argparse
import re
from pathlib import Path
from typing import List

import yaml
from pycparser.c_ast import FuncDecl, NodeVisitor, PtrDecl, TypeDecl, Typedef
from pycparser.c_generator import CGenerator
from pycparser.c_parser import CParser

from .proto import Argument, Function, PipelineCProto, ReturnType

# Regex that's used to remove all comments within the source headers
comment_re = re.compile(r"/\*.*?\*/|//([^\n\\]|\\.)*?$", re.DOTALL | re.MULTILINE)
# Regex that's used to identify functions with an owning return type
owning_func_re = re.compile(
    r"\/\*\s*owning\s*\*\/\s*(?P<function_name>[\w_]+)",
    re.DOTALL | re.MULTILINE,
)
# Regex matching function names in PipelineC
name_re = re.compile("[a-zA-Z0-9_]+$")


class Visitor(NodeVisitor):
    def __init__(self, owning_return_functions: List[str]):
        super().__init__()
        self.owning_return_functions = owning_return_functions
        self.c_gen = CGenerator()
        self.functions: List[Function] = []
        self.types: List[str] = []

    def visit_FuncDecl(self, node: FuncDecl):  # noqa: N802
        name = self.get_name(node)
        return_type = self.c_gen.visit(node.type)
        arguments = []
        if node.args is not None:
            for arg in node.args.params:
                arguments.append(self.parse_argument(arg))
        self.functions.append(
            Function(name, arguments, ReturnType(return_type, name in self.owning_return_functions))
        )

    def visit_Typedef(self, node: Typedef):  # noqa: N802
        if node.name not in {"bool", "uint8_t", "uint32_t", "uint64_t"}:
            self.types.append(node.name)

    def get_name(self, node: PtrDecl | TypeDecl) -> str:
        if isinstance(node.type, TypeDecl):
            return node.type.declname
        else:
            return node.type.type.declname

    def parse_argument(self, arg):
        string = self.c_gen.visit(arg)
        type_ = ""
        if string.endswith("[]"):
            type_ = "[]"
            string = string[:-2]

        name = name_re.search(string)[0]
        type_ = name_re.sub("", string) + type_
        return Argument(name, type_.rstrip())


def parse_headers(headers: List[Path]) -> PipelineCProto:
    # Fixup definitions for types not present in C99
    text = """
typedef struct bool bool;
typedef struct uint8_t uint8_t;
typedef struct uint32_t uint32_t;
typedef struct uint64_t uint64_t;
"""
    for header in headers:
        text += header.read_text()

    owning_return_functions = [m["function_name"] for m in owning_func_re.finditer(text)]
    text = comment_re.sub("", text)
    text = "".join(ln if not ln.startswith("#") else "\n" for ln in text.splitlines(True))

    parser = CParser()
    visitor = Visitor(owning_return_functions)
    visitor.visit(parser.parse(text, "input"))
    return PipelineCProto(visitor.functions, visitor.types)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--header", action="append", type=str, help="Header file to parse")
    parser.add_argument("output", type=str, help="Output File")
    args = parser.parse_args()
    if len(args.header) == 0:
        raise ValueError("At least one header must be specified")
    proto = parse_headers([Path(p) for p in args.header])
    with open(args.output, "w") as output:
        yaml.safe_dump(proto.to_dict(), output)


if __name__ == "__main__":
    main()
