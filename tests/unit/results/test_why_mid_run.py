"""Why each line is missed, worked out from a run's inputs so far, as a run part way through
reads it, with a stop of the caller's own."""

import time
from pathlib import Path

from pyct.core.foundation.branch import ForkSite, Site
from pyct.results.record import why_uncovered
from pyct.results.why import Reason, WhyEntry
from tests.unit.results.test_record_why import SOURCE, run_of


def test_the_causes_of_a_run_part_way_are_the_finished_run_s(tmp_path: Path) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    result = run_of(str(file), Site(file=str(file), line=3, col=7))

    causes = why_uncovered(result.records, result.misses, result.untried, result.coverage, None)

    assert causes == result.why_uncovered


def test_a_stop_that_has_come_leaves_every_line_not_worked_out(tmp_path: Path) -> None:
    file = tmp_path / "m.py"
    file.write_text(SOURCE)
    result = run_of(str(file), Site(file=str(file), line=3, col=7))
    untried = {ForkSite(Site(file=str(file), line=3, col=7)): 1}

    causes = why_uncovered(
        result.records, result.misses, untried, result.coverage, time.monotonic() - 1
    )

    assert causes == (WhyEntry(file=str(file), lines=(1, 4), reason=Reason.NOT_WORKED_OUT),)
