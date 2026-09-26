"""A failure's reason as a record keeps it: the same on every run, and in every checkout.

A side's reason can name what differs between two runs of the same row: the memory address
in an object's repr, and the absolute path of this checkout or the legacy checkout. The
stable form writes a path under this checkout or the legacy checkout from ``<v2>`` or
``<legacy>`` onwards, each address as ``<address>``, and any other absolute path as
``<elsewhere>/`` and its file name. The exception type and message keep every other word.

A checkout is found by its whole path, spaces and brackets too, the longest path first, so a
file in a checkout that sits inside the other one is written from the inner checkout.
"""

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from tools.compare_coverage.entries import Origin

ADDRESS = re.compile(r"\b0x[0-9a-fA-F]+\b")

# a path ends at a space, a quote, a comma, a colon, a semicolon or a bracket
END = r"\s'\",:;()\[\]<>"

# a path starts at a slash not joined to a word or a path before it
START = r"(?<![\w.~<>/-])"

ABSOLUTE_PATH = re.compile(rf"{START}/[^{END}]*")


def stable_reason(reason: str, roots: Mapping[Origin, Path]) -> str:
    """``reason`` with its checkouts, addresses and other absolute paths written the stable way."""
    text = reason
    for form, origin in _root_forms(roots):
        text = re.sub(rf"{START}{re.escape(form)}(?=[/{END}]|$)", f"<{origin.value}>", text)
    text = ADDRESS.sub("<address>", text)
    return ABSOLUTE_PATH.sub(lambda path: f"<elsewhere>/{PurePosixPath(path.group()).name}", text)


def _root_forms(roots: Mapping[Origin, Path]) -> list[tuple[str, Origin]]:
    """Each checkout's path as given and resolved, the longest first."""
    forms = {str(form): origin for origin, root in roots.items() for form in (root, root.resolve())}
    return sorted(forms.items(), key=lambda form: len(form[0]), reverse=True)
