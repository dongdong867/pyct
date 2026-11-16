"""The rewrites tool tells a method's ``self`` apart as an object: the request shows the instance
as its class and the dict each input builds it from, and a rewrite may read its fields."""

import time

from pyct.binding.builds import SelfBuild
from pyct.binding.hints import inside_of
from pyct.core.foundation.branch import Site
from pyct.execution.execute import ExecutionResult
from pyct.rewrite.condition import Rewrite, rewrite_code
from pyct.run.model_runs import Building
from pyct.run.rewrites import _Child
from pyct.run.stuck import Outcome
from tests.acceptance.llm_rewrites import FakeRewrites
from tests.unit.rewrite.orders import Order
from tests.unit.run.test_rewrites_kept_visits import (
    asks,  # noqa: F401
    moment_at,
    picked,
    tool_for,
    visits,
)

# `Cart.total(self, discount)`: `if discount > 10:` on line 15
TOTAL = "targets.classes.cart::Cart.total"
# `Till.pay(self)`: `if float(self.code) == 1e-30:` on line 59
TILL_PAY = "targets.rewrites.objects::Till.pay"


# llm-rewrite-hint-built-object-each-built-object-counts
def test_a_method_s_self_is_shown_as_its_class_and_the_dict_it_is_built_from() -> None:
    provider = FakeRewrites(["I cannot rewrite it."])
    tool, file = tool_for(TOTAL, provider)
    site = Site(file, 15, 11)
    picked(
        tool,
        visits(site, ([">", "discount", 10], False)),
        {"self": {"owner": "ann"}, "discount": 0},
    )
    entry, moment = moment_at(site, True)

    handled = tool.take((entry,), moment)

    assert handled.outcomes == (Outcome.GAVE_UP,)
    request = provider.requests[0]
    assert dict(request.args) == {
        "self": '<Cart object, built from {"owner": "ann"}>',
        "discount": "0",
    }
    assert request.unreadable == ()


# llm-rewrite-object-fields-reads-self
def test_a_method_that_takes_only_self_is_asked_with_self_as_its_parameter() -> None:
    provider = FakeRewrites(["I cannot rewrite it."])
    tool, file = tool_for(TILL_PAY, provider)
    site = Site(file, 59, 11)
    aimed = visits(site, (["==", ["float", "code"], 1e-30], False))
    picked(tool, aimed, {"self": {"code": "0"}})
    entry, moment = moment_at(site, True)

    handled = tool.take((entry,), moment)

    assert handled.outcomes == (Outcome.GAVE_UP,)
    assert provider.requests
    assert {request.unreadable for request in provider.requests} == {()}
    assert dict(provider.requests[0].args) == {"self": '<Till object, built from {"code": "0"}>'}


def test_a_rewrite_reads_self_when_the_seed_names_it_after_another_parameter() -> None:
    reads = 'self.code == "1e-30" and n > 0'
    rewrite = rewrite_code(reads, ("n", "self"), "<rewrite m:2:7>", (), ("self",))
    assert isinstance(rewrite, Rewrite)
    checks = {"self": inside_of(Order).keys}
    building = Building(checks=checks, self_build=SelfBuild(Order, "self"))

    done = _Child(time.monotonic() + 5, building).run(rewrite.code, {"n": 1, "self": {"code": "0"}})

    assert isinstance(done, ExecutionResult)
    assert done.failure is None, done.failure
