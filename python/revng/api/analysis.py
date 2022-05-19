#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

from typing import Any, Dict, Generator, Optional

from ._capi import _api, ffi
from .kind import Kind
from .utils import make_generator, make_python_string


class Analysis:
    def __init__(self, analysis):
        self._analysis = analysis

    @property
    def name(self) -> str:
        _name = _api.rp_analysis_get_name(self._analysis)
        return make_python_string(_name)

    def get_arguments_count(self) -> int:
        return _api.rp_analysis_get_arguments_count(self._analysis)

    def arguments(self) -> Generator["AnalysisArgument", None, None]:
        return make_generator(self.get_arguments_count(), lambda idx: AnalysisArgument(self, idx))

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arguments": [a.as_dict() for a in self.arguments()]}


class AnalysisArgument:
    def __init__(self, analysis: Analysis, index: int):
        self.analysis = analysis
        self.index = index

    @property
    def name(self):
        _name = _api.rp_analysis_get_argument_name(self.analysis._analysis, self.index)
        return make_python_string(_name)

    def acceptable_kinds(self) -> Generator[Kind, None, None]:
        return make_generator(self.acceptable_kinds_count(), self._get_acceptable_kind_from_index)

    def acceptable_kinds_count(self) -> int:
        return _api.rp_analysis_get_argument_acceptable_kinds_count(
            self.analysis._analysis, self.index
        )

    def _get_acceptable_kind_from_index(self, idx) -> Optional[Kind]:
        _kind = _api.rp_analysis_get_argument_acceptable_kind(
            self.analysis._analysis, self.index, idx
        )
        return Kind(_kind) if _kind != ffi.NULL else None

    def as_dict(self):
        return {
            "name": self.name,
            "acceptable_kinds": [k.as_dict() for k in self.acceptable_kinds()],
        }
