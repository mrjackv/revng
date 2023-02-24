#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from base64 import b64decode
from pathlib import Path
from subprocess import run
from tempfile import NamedTemporaryFile
from typing import Dict, List, Tuple, cast

import jinja2
import yaml

from .proto import ArgumentType, Function, PipelineCProto, Trace, TraceCommand

SCRIPT_DIR = Path(__file__).parent
COMPILE_COMMAND = ["gcc", "-Wall", "-lrevngPipelineC", "-lrevngSupport", "-O0", "-g", "-o"]


class RuntimeContext:
    def __init__(self, proto: PipelineCProto, root: Path):
        self.root = root
        self.proto = proto
        self.functions = {f.name: f for f in proto.functions}
        self.var_counter = 0
        self.variables: Dict[Tuple[str | None, str], str] = {}
        self.opaque_pointers = set()
        for type_ in proto.opaque_pointers:
            self.opaque_pointers.add(f"{type_} *")
            self.opaque_pointers.add(f"const {type_} *")
        self.temporary_directories: List[str] = []

    def print_epilogue(self):
        return "".join(f"remove_directory({e});\n" for e in self.temporary_directories)

    def next_var(self, prefix: str):
        ret = f"{prefix}{self.var_counter}"
        self.var_counter += 1
        return ret

    def create_variable(self, ptr: str | None, type_: str):
        assert ptr is None or ptr.startswith("P0x")
        ret = self.next_var("var")
        self.variables[(ptr, type_.removeprefix("const "))] = ret
        return ret

    def create_temp_string(
        self, var: str, function_name: str, argument_name: str
    ) -> Tuple[str, str]:
        varname = self.next_var("temp")
        if (
            function_name in self.proto.length_hints
            and argument_name in self.proto.length_hints[function_name]
        ):
            # Handle buffer
            bytestring = b64decode(var)
            byte_array = ", ".join(str(b) for b in bytestring)
            decl = f"char {varname}[{len(bytestring)}] = {{ {byte_array } }};"
        else:
            # Handle plain string
            decl = f'char * {varname} = "{var}";'
        return (varname, decl)

    def create_temp_argument_list(self, type_: str, var: List[str] | List[int]) -> Tuple[str, str]:
        """Creates a complex temporary argument"""
        assert type_.endswith("[]")
        varname = self.next_var("temp")
        element_type = type_[:-2]
        if "int" in type_:
            elements = [str(i) for i in var]
        elif "char" in type_:
            elements = [f'"{elem}"' for elem in var]
        else:
            elements = [self.get_variable(ptr, element_type) for ptr in cast(List[str], var)]

        # We add a sentinel NULL at the end of array as a primitive OOB detection
        elements_joined = "".join(f"{e}, " for e in elements)
        decl = f"{element_type} {varname}[{len(var) + 1}] = {{ {elements_joined}0 }};"
        return (varname, decl)

    def get_variable(self, ptr: str, type_: str):
        assert ptr.startswith("P0x")
        if ptr == "P0x0":
            return "NULL"
        return self.variables[(ptr, type_.removeprefix("const "))]

    def print_command(self, cmd: TraceCommand):
        function_data = self.functions[cmd.name]

        # Print the function invocation, with arguments
        arguments_decls = []
        ret = f"{cmd.name}("
        if cmd.arguments is not None:
            arguments = []
            for i, arg in enumerate(cmd.arguments):
                varname, decl = self.print_argument(function_data, arg, i)
                arguments.append(varname)
                if decl is not None:
                    arguments_decls.append(decl)
            ret += ", ".join(arguments)
        ret += ");"

        # Compute the return variable, this is done afterwards to avoid pointer
        # aliasing
        return_type = function_data.return_type.type_
        if return_type.endswith("*"):
            var = self.create_variable(cast(str | None, cmd.return_), return_type)
            ret = f"{return_type} {var} = " + ret
            # Add an assertion checking if the returned pointer is NULL or not
            if cmd.return_ == "P0x0":
                ret += f"\nrevng_assert({var} == NULL);"
            else:
                ret += f"\nrevng_assert({var} != NULL);"
        elif return_type != "void":
            # The return type is an integral, add an assertion to check that
            # the value is correct
            varname = self.next_var("check")
            return_ = cmd.return_ if cmd.return_ is not None else 0
            if return_type == "bool":
                ret = f"bool {varname} = " + ret
                ret += f"\nrevng_assert({varname} == {int(cast(bool, return_))});"
            elif return_type in {"uint8_t", "uint32_t", "uint64_t"}:
                # Artifact generation is not stable, rp_buffer_size will, for sure,
                # report a different size on different runs
                if cmd.name != "rp_buffer_size":
                    ret = f"{return_type} {varname} = " + ret
                    ret += f"\nrevng_assert({varname} == {cast(int, return_)});"
            else:
                raise ValueError(f"Unknown return type: {return_type}")
        else:
            assert cmd.return_ is None

        ret = "\n".join(arguments_decls) + "\n" + ret
        return ret

    def print_argument(self, data: Function, arg: ArgumentType, i: int) -> Tuple[str, str | None]:
        if arg_function := getattr(self, f"handle_{data.name}_{data.arguments[i].name}", None):
            return arg_function(data, arg, i)
        else:
            return self._print_argument(data, arg, i)

    def _print_argument(self, data: Function, arg: ArgumentType, i: int) -> Tuple[str, str | None]:
        if isinstance(arg, str):
            if arg.startswith("P0x"):
                return (self.get_variable(arg, data.arguments[i].type_), None)
            else:
                return self.create_temp_string(arg, data.name, data.arguments[i].name)
        elif isinstance(arg, int):
            return (str(arg), None)
        elif isinstance(arg, list):
            return self.create_temp_argument_list(data.arguments[i].type_, arg)
        else:
            raise ValueError(f"Cannot create argument from: {arg}")

    def patch_path(self, path: str) -> str:
        """Patch a path string with the proper root-relative path"""
        assert (pos := path.rfind("root")) > 0
        return str(self.root / path[pos + 5 :])

    # Function "patches", these mainly handle:
    # * Paths relative to ORCHESTRA_ROOT that are surely invalid
    # * Temporary directories, which surely don't exist
    def handle_rp_initialize_libraries_path(self, data: Function, arg: ArgumentType, i: int):
        return self._print_argument(data, [self.patch_path(p) for p in cast(list, arg)], i)

    def handle_rp_manager_create_pipelines_path(self, data: Function, arg: ArgumentType, i: int):
        return self._print_argument(data, [self.patch_path(p) for p in cast(list, arg)], i)

    def handle_rp_manager_create_execution_directory(
        self, data: Function, arg: ArgumentType, i: int
    ):
        return self._workdir_variable()

    def handle_rp_manager_create_from_string_execution_directory(
        self, data: Function, arg: ArgumentType, i: int
    ):
        return self._workdir_variable()

    def _workdir_variable(self):
        varname = self.next_var("workdir")
        self.temporary_directories.append(varname)
        decl = f"const char * {varname} = mkdtemp(workdir_template);\n"
        decl += f'printf("Workdir is %s\\n", {varname});'
        return (varname, decl)


def command_comment(cmd: TraceCommand):
    yaml_str = yaml.safe_dump(cmd.to_dict())
    return "".join(f"// {line}\n" for line in yaml_str.splitlines())


def compile_trace(
    trace_file: Path, proto_file: Path, root: Path, c_file: Path | None, executable: Path | None
):
    if c_file is None and executable is None:
        raise ValueError("Cannot run with both c_file and executable set to None")

    if c_file is None:
        tmp_c_file = NamedTemporaryFile("w", suffix=".c")
        c_file = Path(tmp_c_file.name)

    with open(trace_file) as trace_f:
        raw_trace = yaml.safe_load(trace_f)

    if raw_trace["version"] != 1:
        raise ValueError(f"Unsupported trace version: {raw_trace['version']}")

    trace = Trace.from_dict(raw_trace)

    with open(proto_file) as proto_f:
        proto = PipelineCProto.from_dict(yaml.safe_load(proto_f))

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(SCRIPT_DIR))
    env.filters["command_comment"] = command_comment
    template = env.get_template("trace_runner.c.j2")
    context = RuntimeContext(proto, root)

    c_file.write_text(
        template.render(
            commands=trace.commands,
            print_command=context.print_command,
            print_epilogue=context.print_epilogue,
        )
    )

    if executable is not None:
        run([*COMPILE_COMMAND, str(executable), str(c_file)], check=True)
