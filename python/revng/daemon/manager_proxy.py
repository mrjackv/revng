#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import contextlib
import os
from tempfile import mkdtemp
from typing import Literal, Union

from revng.api.manager import Manager


class ManagerProxy(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__fifos = []
        self.__begin_step = self.get_step("begin")
        assert self.__begin_step is not None

        if "REVNG_NOTIFY_FIFOS" in os.environ:
            for fifo_file in os.environ["REVNG_NOTIFY_FIFOS"].split(","):
                self.__fifos.append(open(fifo_file, "w"))  # noqa: SIM115

    def set_input(self, *args, **kwargs):
        result = super().set_input(*args, **kwargs)
        self.__sync("begin")
        return result

    def run_analysis(self, *args, **kwargs):
        result = super().run_analysis(*args, **kwargs)
        self.__sync("context")
        return result

    def run_all_analyses(self, *args, **kwargs):
        result = super().run_all_analyses()
        self.__sync("context")
        return result

    def __sync(self, sync_type: Union[Literal["begin"], Literal["context"]]):
        if sync_type == "begin":
            with contextlib.suppress(Exception):
                for fifo in self.__fifos:
                    tmpdir = mkdtemp()
                    self.__begin_step.save(tmpdir)
                    fifo.write(f"PUSH begin {tmpdir}\n")
                    fifo.flush()
        elif sync_type == "context":
            with contextlib.suppress(Exception):
                tmpdir = mkdtemp()
                self.save_context(tmpdir)
                fifo.write(f"PUSH context {tmpdir}\n")
                fifo.flush()
        else:
            # Ignore
            pass

    def __del__(self):
        for fifo in self.__fifos:
            fifo.close()
