"""The stderr line each summaries note gives, the loop's site written ``file:line``."""

import pytest

from pyct.cli.llm import note_line
from pyct.core.foundation.branch import Site
from pyct.run.notes import (
    SummaryChecked,
    SummaryFailed,
    SummaryNote,
    SummaryRead,
    SummarySkipped,
)

SITE = Site("/t/m.py", 10, 4)


@pytest.mark.parametrize(
    ("note", "line"),
    [
        (
            SummaryRead(SITE, 't = t + s.count("z")'),
            'llm: summary for the loop at /t/m.py:10: t = t + s.count("z")',
        ),
        (
            SummaryRead(SITE, "n = len(s)\nif n > 3:\n    n = 3\nreturn {'t': n}", below=True),
            "llm: summary for the loop at /t/m.py:10:\n    n = len(s)\n    if n > 3:\n"
            "        n = 3\n    return {'t': n}",
        ),
        (
            SummaryChecked(SITE, 4),
            "llm: summary for the loop at /t/m.py:10: checked on 4 past runs",
        ),
        (
            SummaryFailed(SITE, 2, "at input 1, t was 0, the formula gave 2"),
            "llm: summary for the loop at /t/m.py:10, try 2:"
            " at input 1, t was 0, the formula gave 2",
        ),
        (
            SummarySkipped(SITE, "cannot fork"),
            "llm: summary for the loop at /t/m.py:10 skipped: cannot fork",
        ),
    ],
)
def test_each_summaries_note_has_its_line(note: SummaryNote, line: str) -> None:
    assert note_line(note) == line


def test_a_character_a_terminal_reads_is_escaped_on_each_line() -> None:
    read = SummaryRead(SITE, 'x = "\x1b[2J"\nreturn {"t": x}', below=True)
    failed = SummaryFailed(SITE, 1, "it raised at input 2: ValueError: \x1b[31m")

    assert note_line(read) == (
        'llm: summary for the loop at /t/m.py:10:\n    x = "\\x1b[2J"\n    return {"t": x}'
    )
    assert note_line(failed) == (
        "llm: summary for the loop at /t/m.py:10, try 1:"
        " it raised at input 2: ValueError: \\x1b[31m"
    )
