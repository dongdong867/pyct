"""The stderr line each summaries note gives, the loss site written ``the call NAME at
file:line:col``."""

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
AT = "llm: summary for the call __pow__ at /t/m.py:10:4"
NAME = "__pow__"


@pytest.mark.parametrize(
    ("note", "line"),
    [
        (
            SummaryRead(SITE, "answer = n % 4", call=NAME),
            f"{AT}: answer = n % 4",
        ),
        (
            SummaryRead(
                SITE, "q = n % 4\nif q > 2:\n    q = 2\nreturn {'answer': q}", True, call=NAME
            ),
            f"{AT}:\n    q = n % 4\n    if q > 2:\n        q = 2\n    return {{'answer': q}}",
        ),
        (
            SummaryChecked(SITE, 4, call=NAME),
            f"{AT}: checked on 4 past runs",
        ),
        (
            SummaryChecked(SITE, 4, 1, call=NAME),
            f"{AT}: checked on 4 past runs, 1 of them not shown",
        ),
        (
            SummaryFailed(SITE, 2, "at input 1, answer was 3, the formula gave 9", call=NAME),
            f"{AT}, try 2: at input 1, answer was 3, the formula gave 9",
        ),
        (
            SummarySkipped(SITE, "cannot fork", call=NAME),
            f"{AT} skipped: cannot fork",
        ),
        (
            SummaryNotUsed(SITE, "inputs run in pyct's own process", call=NAME),
            f"{AT} not used: inputs run in pyct's own process",
        ),
        (
            SummaryNotUsed(SITE, "answer\x1b is a list", call=NAME),
            f"{AT} not used: answer\\x1b is a list",
        ),
        (
            SummaryDropped(SITE, 9, "answer was 5, the formula gave 6", call=NAME),
            f"{AT} dropped at input 9: answer was 5, the formula gave 6",
        ),
        (
            SummaryDropped(SITE, 3, "the formula gave no answer\x1b", call=NAME),
            f"{AT} dropped at input 3: the formula gave no answer\\x1b",
        ),
    ],
)
def test_each_summaries_note_has_its_line(note: SummaryNote, line: str) -> None:
    assert note_line(note) == line


def test_a_character_a_terminal_reads_is_escaped_on_each_line() -> None:
    read = SummaryRead(SITE, 'x = "\x1b[2J"\nreturn {"answer": x}', True, call=NAME)
    failed = SummaryFailed(SITE, 1, "it raised at input 2: ValueError: \x1b[31m", call=NAME)

    assert note_line(read) == f'{AT}:\n    x = "\\x1b[2J"\n    return {{"answer": x}}'
    assert note_line(failed) == f"{AT}, try 1: it raised at input 2: ValueError: \\x1b[31m"
