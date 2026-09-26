"""A failure's reason as a record keeps it: the same on every run, and in every checkout.

A side's reason can name what differs between two runs of the same row: the memory address
in an object's repr, and the absolute path of this checkout or the legacy checkout. The
stable form writes each address as ``<address>``, a path under this checkout or the legacy
checkout from ``<v2>`` or ``<legacy>`` onwards, and any other absolute path as
``<elsewhere>/`` and its file name. The exception type and message keep every other word.
"""

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from tools.compare_coverage.entries import Origin

ADDRESS = re.compile(r"\b0x[0-9a-fA-F]+\b")

# a slash not joined to a word before it starts an absolute path, which runs to a space,
# a quote, a comma, a colon or a bracket
ABSOLUTE_PATH = re.compile(r"(?<![\w.~<>-])/[^\s'\",:;()\[\]<>]*")


def stable_reason(reason: str, roots: Mapping[Origin, Path]) -> str:
    """``reason`` with its addresses and absolute paths written the stable way."""
    text = ADDRESS.sub("<address>", reason)
    return ABSOLUTE_PATH.sub(lambda path: _stable_path(path.group(), roots), text)


def _stable_path(path: str, roots: Mapping[Origin, Path]) -> str:
    for origin, root in roots.items():
        for form in {str(root), str(root.resolve())}:
            if path == form or path.startswith(f"{form}/"):
                return f"<{origin.value}>{path[len(form) :]}"
    return f"<elsewhere>/{PurePosixPath(path).name}"
