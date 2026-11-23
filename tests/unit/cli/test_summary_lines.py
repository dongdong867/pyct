"""The stderr line each summaries note gives, the loop's site written ``file:line``."""

import pytest

from pyct.cli.llm import note_line
from pyct.core.foundation.branch import Site
from pyct.run.notes import (
    SummaryChecked,
    SummaryDropped,
    SummaryFailed,
    SummaryNote,
    SummaryNotUsed,
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
            SummaryChecked(SITE, 4, 1),
            "llm: summary for the loop at /t/m.py:10: checked on 4 past runs, 1 of them not shown",
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
        (
            SummaryNotUsed(SITE, "inputs run in pyct's own process"),
            "llm: summary for the loop at /t/m.py:10 not used: inputs run in pyct's own process",
        ),
        (
            SummaryNotUsed(SITE, "s\x1b is a list"),
            "llm: summary for the loop at /t/m.py:10 not used: s\\x1b is a list",
        ),
        (
            SummaryDropped(SITE, 9, "t was 5, the formula gave 6"),
            "llm: summary for the loop at /t/m.py:10 dropped at input 9: t was 5,"
            " the formula gave 6",
        ),
        (
            SummaryDropped(SITE, 3, "the formula gave no t\x1b"),
            "llm: summary for the loop at /t/m.py:10 dropped at input 3: the formula gave no"
            " t\\x1b",
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
