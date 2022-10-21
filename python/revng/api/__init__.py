#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import atexit
from typing import Optional

from revng.support import AnyPath

from ._capi import initialize, shutdown
from .manager import Manager
from .rank import Rank

__all__ = ["Manager", "Rank", "initialize", "shutdown"]

_initialized = False


def make_manager(workdir: Optional[AnyPath] = None):
    global _initialized
    if not _initialized:
        initialize()
        atexit.register(shutdown)
        _initialized = True
    return Manager(workdir)
