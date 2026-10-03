"""An input's line is what json.dumps writes for it, however pyct puts its forks together."""

import json

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render
from pyct.results.printed import CUT, PrintedForks, printed_forks
from pyct.results.record import Aim, DowngradeCount, InputRecord, Source

COVERAGE = Coverage(covered={"m.py": frozenset({6, 5})}, lines={"m.py": frozenset(range(1, 8))})
LOOP = Site(file="m.py", line=2, col=10)


def _at(site: Site) -> dict[str, object]:
    return {"file": site.file, "line": site.line, "col": site.col}


def _dumped(record: InputRecord, coverage: Coverage, printed: PrintedForks) -> str:
    """The line as one json.dumps of the whole payload writes it."""
    failure, aim = record.failure, record.aim
    pairs = zip(record.forks, printed.expressions, strict=True)
    payload = {
        "args": record.args,
        "forks": [{**_at(fork.site), "taken": fork.taken, "expression": e} for fork, e in pairs],
        "covered": {file: sorted(lines) for file, lines in coverage.covered.items()},
        "total": dict(coverage.total),
        "failure": None
        if failure is None
        else {"kind": failure.kind.value, "detail": failure.detail},
        "downgrades": [
            {"name": d.name, "count": d.count, **_at(d.site)} for d in record.downgrades
        ],
        "source": record.source.value,
        "aim": None if aim is None else {**_at(aim.site), "position": aim.position},
        "mismatch_at": record.mismatch_at,
    }
    return json.dumps(payload)


def _countdown(passes: int, site: Site = LOOP) -> tuple[Branch, ...]:
    value: Expression = "x"
    forks = []
    for i in range(passes + 1):
        forks.append(Branch(expression=[">", value, 0], taken=i < passes, site=site))
        value = ["-", value, 1]
    return tuple(forks)


FORKS = {
    "none": (),
    "leaves and floats": tuple(
        Branch(expression=leaf, taken=bool(i % 2), site=Site(f"m{i % 3}.py", i, 7))
        for i, leaf in enumerate(["flag", 7, 2.5, float("nan"), float("-inf"), -0.0, True, None])
    ),
    "a long loop": _countdown(2_000),
    "files past ASCII": _countdown(400, Site('été "q" \\ \udcff.py', 9, 1))
    + _countdown(3, Site("m.py", 1, 0)),
}

RECORDS = {
    "a seed": {"args": {"x": 1}},
    "args that read as a line's keys": {
        "args": {"s": '"forks": [], "covered": {}', "t": "é\n\udcff", "n": [1, {"k": None}]}
    },
    "an aimed input that raised": {
        "args": {"x": 12},
        "failure": Failure(FailureKind.TARGET_RAISED, "ValueError: é"),
        "downgrades": (DowngradeCount("__xor__", 3, Site("m.py", 3, 12)),),
        "source": Source.SOLVER,
        "aim": Aim(site=LOOP, position=4),
        "mismatch_at": 2,
    },
}


@pytest.mark.parametrize("forks", list(FORKS))
@pytest.mark.parametrize("fields", list(RECORDS))
def test_a_line_is_what_json_dumps_writes_for_it(forks: str, fields: str) -> None:
    given = RECORDS[fields]
    record = InputRecord(forks=FORKS[forks], covered_lines=frozenset({5}), **given)  # pyrefly: ignore[bad-argument-type]
    printed = printed_forks(record.forks)

    assert render(record, COVERAGE, printed) == _dumped(record, COVERAGE, printed)


def test_a_cut_part_uncounted_or_counted_is_written_as_json_dumps_writes_it() -> None:
    record = InputRecord(args={"x": 1}, forks=_countdown(2), covered_lines=frozenset({5}))
    printed = PrintedForks(([CUT, None], [CUT, 12], [CUT, 1]), cut_from=0)

    line = render(record, COVERAGE, printed)

    assert line == _dumped(record, COVERAGE, printed)
    assert '"expression": ["...", null]}' in line
