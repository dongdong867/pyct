"""A call's plan made the way a call makes it: the seed bound first, then planned."""

import inspect
from collections.abc import Mapping, Sequence

from pyct.binding.annotations import Check
from pyct.binding.bind import bind_call
from pyct.binding.builds import CallPlan, SelfBuild, plan_call


def planned(
    seed: Mapping[str, object],
    positional: Sequence[inspect.Parameter],
    self_build: SelfBuild | None,
    home: str,
    checks: Mapping[str, Check] | None = None,
) -> CallPlan:
    """The plan of one call of ``seed``, bound with no sink, as ``execute`` plans it."""
    return plan_call(bind_call(seed, [], checks, home), positional, self_build, home, checks)
