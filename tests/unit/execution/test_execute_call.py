"""How execute passes the seed to the call: by name, and by position where the target asks."""

import inspect

from pyct.binding.call import positional_only
from pyct.execution.execute import ExecutionContext, execute


def test_execute_passes_a_positional_only_parameter_by_position() -> None:
    def check(value: str, /, strict: bool = False) -> None:
        if value == "abc":
            return

    positional = positional_only(inspect.signature(check))
    ctx = ExecutionContext(fn=check, file=__file__, positional=positional)

    result = execute(ctx, {"value": "x", "strict": True})

    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [["==", "value", "'abc'"]]


class SignatureGone:
    """A callable whose signature reads once, at load, and never again."""

    @property
    def __signature__(self) -> inspect.Signature:
        raise RuntimeError("signature gone")

    def __call__(self, x: int) -> None:
        if x > 0:
            return


def test_execute_reads_no_signature_of_its_own() -> None:
    # the positional-only parameters come on the context, read when the target was loaded
    ctx = ExecutionContext(fn=SignatureGone(), file=__file__)

    result = execute(ctx, {"x": 1})

    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [[">", "x", 0]]
