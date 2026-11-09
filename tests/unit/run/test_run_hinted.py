"""Through run(), an object under a class hint that names no one class: no call, and each input
fails with the place and the reason."""

import pytest

from pyct.results.failure import FailureKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target

HINTED = "targets.classes.hinted"
NAME_IT = 'name the class to build with "__class__"'


@pytest.mark.parametrize(
    ("function", "args", "detail"),
    [
        ("draw", {"s": {"side": 1}}, f"building s: hint Shape is an abstract class; {NAME_IT}"),
        ("draw", {"s": [1]}, f"building s: hint Shape is an abstract class; {NAME_IT}"),
        ("render", {"d": {}}, f"building d: hint Drawable is a Protocol; {NAME_IT}"),
        (
            "either",
            {"c": {"name": "ann", "age": 30}},
            f"building c: hint Customer | Guest names two classes; {NAME_IT}",
        ),
    ],
)
def test_an_object_a_hint_cannot_build_fails_its_input_unrun(
    function: str, args: dict[str, object], detail: str
) -> None:
    result = run(load_target(f"{HINTED}::{function}"), args, isolation=Isolation.IN_PROCESS)

    (record,) = result.records
    assert record.failure is not None
    assert record.failure.kind is FailureKind.TARGET_RAISED
    assert record.failure.detail == detail
    assert record.forks == () and record.covered_lines == frozenset()
