#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

# This file has the definition of the main structures used by the
# PipelineC-proto system
# Each class has a `from_dict` and `to_dict` method that helps with
# serialization/deserialization

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Argument:
    name: str
    type_: str

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type_}

    @staticmethod
    def from_dict(dict_: dict) -> "Argument":
        return Argument(dict_["name"], dict_["type"])


@dataclass
class ReturnType:
    type_: str
    owning: bool

    def to_dict(self) -> dict:
        return {"type": self.type_, "owning": self.owning}

    @staticmethod
    def from_dict(dict_: dict) -> "ReturnType":
        return ReturnType(dict_["type"], dict_["owning"])


@dataclass
class Function:
    name: str
    arguments: List[Argument]
    return_type: ReturnType

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": [a.to_dict() for a in self.arguments],
            "return_type": self.return_type.to_dict(),
        }

    @staticmethod
    def from_dict(dict_) -> "Function":
        return Function(
            dict_["name"],
            [Argument.from_dict(v) for v in dict_["arguments"]],
            ReturnType.from_dict(dict_["return_type"]),
        )


@dataclass
class PipelineCProto:
    functions: List[Function]
    opaque_pointers: List[str]
    length_hints: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        if len(self.length_hints) == 0:
            self.length_hints = {
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

    def to_dict(self) -> dict:
        return {
            "functions": [f.to_dict() for f in self.functions],
            "opaque_pointers": self.opaque_pointers,
            "length_hints": self.length_hints,
        }

    @staticmethod
    def from_dict(dict_: dict) -> "PipelineCProto":
        lh: dict = {}
        return PipelineCProto(
            [Function.from_dict(f) for f in dict_["functions"]],
            dict_["opaque_pointers"],
            dict_.get("length_hints", lh),
        )


ArgumentType = int | str | List[int] | List[str]


@dataclass
class TraceCommand:
    name: str
    arguments: List[ArgumentType]
    return_: int | str | bool | None

    def to_dict(self):
        return {"name": self.name, "arguments": self.arguments, "return": self.return_}

    @staticmethod
    def from_dict(dict_: dict) -> "TraceCommand":
        return TraceCommand(dict_["name"], dict_["arguments"], dict_["return"])


@dataclass
class Trace:
    version: int
    commands: List[TraceCommand]

    def to_dict(self):
        return {"version": self.version, "commands": [c.to_dict() for c in self.commands]}

    @staticmethod
    def from_dict(dict_: dict) -> "Trace":
        return Trace(dict_["version"], [TraceCommand.from_dict(tc) for tc in dict_["commands"]])
