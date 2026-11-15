"""Whether a plan's path holds its aimed fork's check on the other side: a fork at the aimed
fork's site, of the same kind, whose expression is the same."""

from pyct.branches.plan import Plan, plan
from pyct.core.foundation.branch import Branch, Expression, Site
from pyct.rewrite.ask import holds_its_own_check

CHECK = Site("m.py", 3, 21)
GUARD = Site("m.py", 3, 11)
FLOAT_S: Expression = ["==", ["float", "s"], 1e-30]


def visits(*checks: tuple[Expression, bool], site: Site = CHECK) -> Plan:
    """The plan whose path passes the guard and takes each check at ``site`` in turn, the last
    flipped."""
    forks: list[Branch] = []
    for at, (expression, taken) in enumerate(checks):
        forks.append(Branch([">", ["[]", "items", at], 0], True, GUARD))
        forks.append(Branch(expression, taken, site))
    made = plan(tuple(forks))
    assert made is not None
    return made


def chain(depth: int, leaf: str = "s") -> Expression:
    """A sum one term longer on each pass, built anew on each call."""
    built: Expression = leaf
    for at in range(depth):
        built = ["+", built, at]
    return built


def test_a_path_that_took_the_check_false_and_wants_it_true_holds_it() -> None:
    assert holds_its_own_check(visits((FLOAT_S, False), (["==", ["float", "s"], 1e-30], False)))


def test_a_path_that_took_the_check_true_and_wants_it_false_holds_it() -> None:
    assert holds_its_own_check(visits((FLOAT_S, True), (["==", ["float", "s"], 1e-30], True)))


def test_a_path_that_took_the_check_the_side_the_plan_wants_does_not_hold_it() -> None:
    assert not holds_its_own_check(visits((FLOAT_S, True), (FLOAT_S, False)))


def test_a_first_visit_holds_nothing() -> None:
    assert not holds_its_own_check(visits((FLOAT_S, False)))


def test_a_check_of_a_changing_value_is_not_held() -> None:
    first: Expression = ["==", ["float", ["[]", "items", 0]], 1e-30]
    second: Expression = ["==", ["float", ["[]", "items", 1]], 1e-30]

    assert not holds_its_own_check(visits((first, False), (second, False)))


def test_a_literal_of_another_type_or_bits_is_another_check() -> None:
    assert not holds_its_own_check(visits((["==", "n", 1], False), (["==", "n", 1.0], False)))
    assert not holds_its_own_check(visits((["==", "x", 0.0], False), (["==", "x", -0.0], False)))


def test_the_same_check_at_another_site_is_not_held() -> None:
    elsewhere = Branch(FLOAT_S, False, Site("m.py", 5, 7))
    made = plan((elsewhere, Branch(FLOAT_S, False, CHECK)))
    assert made is not None

    assert not holds_its_own_check(made)


def test_an_operation_s_fork_before_a_raise_is_another_kind_of_fork() -> None:
    raising = Branch(FLOAT_S, False, CHECK, raising=True)
    made = plan((raising, Branch(FLOAT_S, False, CHECK)))
    assert made is not None

    assert not holds_its_own_check(made)


def test_a_check_compared_within_the_limit_is_held() -> None:
    # each pass of the chain is 3 parts, so 30,000 passes compare 90,000 parts
    assert holds_its_own_check(visits((chain(30_000), False), (chain(30_000), False)))


def test_a_check_past_the_limit_is_not_held() -> None:
    # 40,000 passes compare 120,000 parts, past the 100,000 a plan may compare
    assert not holds_its_own_check(visits((chain(40_000), False), (chain(40_000), False)))


def test_the_limit_counts_the_parts_of_every_earlier_visit() -> None:
    # the first visit differs only at its deepest part, which the walk reaches after 50,000
    # parts; the second is the same, and would be told within 75,000 parts on its own
    made = visits((chain(25_000, leaf="t"), False), (chain(25_000), False), (chain(25_000), False))

    assert not holds_its_own_check(made)
