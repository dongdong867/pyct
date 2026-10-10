"""The lines of the target's module that ran while pyct imported it.

pyct's process imports the target once, before any input runs, so the
module's ``def`` lines, decorators and other module-level lines run then and
under no input. They count for the run (``README.md › Rules › covered
lines``), and this is where they are kept.
"""

from __future__ import annotations

import contextlib
import sys
import types
from collections.abc import Generator

from pyct.execution.execute import unused_tool_id


class _Collector:
    """The LINE callback: the lines of one module's file, read as the import makes the module.

    The file is the module's ``__file__`` once ``sys.modules`` holds it, the
    first one read kept from then on. Every other file's code location, and
    each one that runs before the module is made, answers DISABLE, so it
    costs one call however often it runs.
    """

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self.file: str | None = None
        self.lines: set[int] = set()

    def on_line(self, code: types.CodeType, line: int) -> object:
        if self.file is None:
            self.file = getattr(sys.modules.get(self.module_name), "__file__", None)
        if code.co_filename != self.file:
            return sys.monitoring.DISABLE
        self.lines.add(line)
        return None


@contextlib.contextmanager
def import_lines(module_name: str) -> Generator[set[int]]:
    """The lines of ``module_name``'s file that run inside the block, filled as they run.

    For the block that imports the module. A module ``sys.modules`` already
    holds runs nothing as it is imported, so its set stays empty. The tool id
    is given back however the block ends.
    """
    collector = _Collector(module_name)
    monitoring = sys.monitoring
    tool_id = unused_tool_id()
    monitoring.use_tool_id(tool_id, "pyct")
    try:
        monitoring.register_callback(tool_id, monitoring.events.LINE, collector.on_line)
        monitoring.set_events(tool_id, monitoring.events.LINE)
        yield collector.lines
    finally:
        monitoring.set_events(tool_id, 0)
        monitoring.register_callback(tool_id, monitoring.events.LINE, None)
        monitoring.free_tool_id(tool_id)
