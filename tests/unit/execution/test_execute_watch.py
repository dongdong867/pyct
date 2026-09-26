"""execute tells a watch each fact of the call as it happens, before the call ends."""

from pyct.core.branch import Branch
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount


class Heard:
    """A watch that keeps what it was told, in order."""

    def __init__(self) -> None:
        self.told: list[tuple[object, ...]] = []

    def fork(self, branch: Branch) -> None:
        self.told.append(("fork", branch.expression, branch.taken))

    def line(self, number: int) -> None:
        self.told.append(("line", number))

    def downgrade(self, name: str, count: int) -> None:
        self.told.append(("downgrade", name, count))


# compiled under a name of its own, so only its lines are traced, not the watch's
FORKS_THEN_RAISES = """\
def target(x):
    if x < 10:
        x >> 1
    x >> 1
    raise ValueError("late")
"""


def test_execute_tells_the_watch_each_fact_before_the_call_ends() -> None:
    namespace: dict[str, object] = {}
    exec(compile(FORKS_THEN_RAISES, "<watched>", "exec"), namespace)
    target = namespace["target"]
    assert callable(target)
    heard = Heard()
    ctx = ExecutionContext(fn=target, file="<watched>")

    result = execute(ctx, {"x": 3}, watch=heard)

    # every fact reached the watch as it happened, before the raise ended the call
    assert heard.told == [
        ("line", 2),
        ("fork", ["<", "x", 10], True),
        ("line", 3),
        ("downgrade", "__rshift__", 1),
        ("line", 4),
        ("downgrade", "__rshift__", 2),
        ("line", 5),
    ]
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: late")
    assert result.downgrades == (DowngradeCount(name="__rshift__", count=2),)
