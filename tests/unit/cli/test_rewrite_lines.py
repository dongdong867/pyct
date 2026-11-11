"""The stderr line each rewrites note gives, the condition's site written ``file:line:col``."""

import pytest

from pyct.cli.llm import note_line
from pyct.core.foundation.branch import Site
from pyct.rewrite.notes import (
    RewriteDropped,
    RewriteFailed,
    RewriteNote,
    RewriteRead,
    RewriteSkipped,
    RewriteTook,
)

SITE = Site("/t/m.py", 7, 7)


@pytest.mark.parametrize(
    ("note", "line"),
    [
        (RewriteRead(SITE, 's == "1e-30"'), 'llm: rewrite for /t/m.py:7:7: s == "1e-30"'),
        (RewriteTook(SITE), "llm: rewrite for /t/m.py:7:7: took the wanted side"),
        (
            RewriteFailed(SITE, 2, "the solver answered unknown"),
            "llm: rewrite for /t/m.py:7:7, try 2: the solver answered unknown",
        ),
        (RewriteSkipped(SITE, "cannot fork"), "llm: rewrite for /t/m.py:7:7 skipped: cannot fork"),
        (
            RewriteDropped(SITE, 5),
            "llm: rewrite for /t/m.py:7:7 dropped at input 5: took the other side",
        ),
    ],
)
def test_each_rewrites_note_has_its_line(note: RewriteNote, line: str) -> None:
    assert note_line(note) == line
