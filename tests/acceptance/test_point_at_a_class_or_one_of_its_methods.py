"""Acceptance tests for point-at-a-class-or-one-of-its-methods.

Each test spawns ``python -P -m pyct`` through the harness, on the class and the objects of
``targets/classes/cart.py``, or on the classes of ``targets/classes/shop.py``, whose methods run
on an instance each input builds.
"""

import inspect
import json
from collections.abc import Callable

import pytest

from pyct.results.failure import FailureKind
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from targets.classes import cart, shop
from tests.acceptance.harness import (
    forks_of,
    input_lines,
    let_pyct_run_in_process,
    lines_expressions_and_sides,
    numbers_of,
    run_pyct,
    summary_line,
    union_of,
)

MODULE = "targets.classes.cart"
SHOP = "targets.classes.shop"
CART_SEED = '{"self": {"owner": "ann"}, "discount": 5}'
OWNER_IS_ADMIN = ["==", ["[]", "self", "'owner'"], "'admin'"]


def body_lines(function: Callable[..., object]) -> set[int]:
    """The lines of a function's body: every line of its source after the ``def``."""
    source, start = inspect.getsourcelines(function)
    return set(range(start + 1, start + len(source)))


def line_of(function: Callable[..., object], text: str) -> int:
    """The line of a function's source that holds ``text``."""
    source, start = inspect.getsourcelines(function)
    return next(start + at for at, line in enumerate(source) if text in line)


def self_of(line: dict[str, object]) -> dict[str, object]:
    """The constructor arguments a printed line's ``self`` holds."""
    args = line["args"]
    assert isinstance(args, dict), line
    fields = args["self"]
    assert isinstance(fields, dict), line
    return fields


def arg_of(line: dict[str, object], name: str) -> object:
    """One argument off a printed line."""
    args = line["args"]
    assert isinstance(args, dict), line
    return args[name]


def above(value: object, bound: int) -> bool:
    """Whether a value off a printed line is an int above ``bound``."""
    return isinstance(value, int) and not isinstance(value, bool) and value > bound


# point-at-a-class-or-one-of-its-methods-runs-a-method-on-an-instance-the-seed-builds, in an
# input's own process and in pyct's
@pytest.mark.parametrize("where", [[], ["--in-process"]], ids=["isolated", "in-process"])
def test_runs_a_method_on_an_instance_the_seed_builds(where: list[str]) -> None:
    result = run_pyct(f"{MODULE}::Cart.total", "--args", CART_SEED, *where)

    assert result.returncode == 0, result.stderr
    first, *solved = lines = input_lines(result.stdout)
    assert forks_of(first)[0]["expression"] == OWNER_IS_ADMIN
    assert any(self_of(line) == {"owner": "admin"} for line in solved), result.stdout
    assert any(above(arg_of(line, "discount"), 10) for line in solved), result.stdout
    forks = [line for line in result.stderr.splitlines() if line.startswith("fork ")]
    assert any("  self['owner'] == 'admin'  " in line for line in forks), result.stderr
    [(_, covered)] = union_of(lines).items()
    assert body_lines(cart.Cart.__init__) | body_lines(cart.Cart.total) <= set(covered)


# point-at-a-class-or-one-of-its-methods-writes-an-input-that-runs-again
def test_writes_an_input_that_runs_again() -> None:
    spec = f"{MODULE}::Cart.total"
    solved = input_lines(run_pyct(spec, "--args", CART_SEED).stdout)[1:]
    admin = next(line for line in solved if self_of(line) == {"owner": "admin"})

    again = run_pyct(spec, "--args", json.dumps(admin["args"]))

    assert again.returncode == 0, again.stderr
    seed_line = input_lines(again.stdout)[0]
    assert seed_line["args"] == admin["args"]
    assert lines_expressions_and_sides(seed_line) == lines_expressions_and_sides(admin)


# point-at-a-class-or-one-of-its-methods-builds-self-from-the-named-class
def test_builds_self_from_the_named_class() -> None:
    result = run_pyct(f"{SHOP}::Cart.describe", "--args", '{"self": {"owner": "ann"}}')

    assert result.returncode == 0, result.stderr
    first, *solved = input_lines(result.stdout)
    line = line_of(shop.Cart.label, 'self.owner == "admin"')
    assert (line, OWNER_IS_ADMIN, False) in lines_expressions_and_sides(first), result.stdout
    taken = [
        answer
        for answer in solved
        if (line, OWNER_IS_ADMIN, True) in lines_expressions_and_sides(answer)
    ]
    assert taken, result.stdout


# point-at-a-class-or-one-of-its-methods-keeps-the-keys-of-self
def test_keeps_the_keys_of_self() -> None:
    result = run_pyct(f"{SHOP}::Box.size", "--args", '{"self": {"w": 1}}')

    assert result.returncode == 0, result.stderr
    first, *solved = lines = input_lines(result.stdout)
    assert any(above(self_of(line)["w"], 3) for line in solved), result.stdout
    assert all(list(self_of(line)) == ["w"] for line in lines), result.stdout
    assert not any("TypeError" in json.dumps(line["failure"]) for line in lines), result.stdout


# point-at-a-class-or-one-of-its-methods-fills-a-left-out-default
def test_fills_a_left_out_default() -> None:
    result = run_pyct(f"{SHOP}::Member.price", "--args", '{"self": {"name": "ann"}}')

    assert result.returncode == 0, result.stderr
    first, *solved = lines = input_lines(result.stdout)
    assert first["args"] == {"self": {"name": "ann", "vip": False}}
    assert any(line["args"] == {"self": {"name": "ann", "vip": True}} for line in solved), (
        result.stdout
    )
    assert not any("tags" in self_of(line) for line in lines), result.stdout


# point-at-a-class-or-one-of-its-methods-names-self-by-the-first-parameter
def test_names_self_by_the_first_parameter() -> None:
    spec = f"{SHOP}::Till.total"

    named = run_pyct(spec, "--args", '{"this": {"owner": "ann"}, "discount": 5}')
    unnamed = run_pyct(spec, "--args", CART_SEED)

    assert named.returncode == 0, named.stderr
    this_is_admin = ["==", ["[]", "this", "'owner'"], "'admin'"]
    assert forks_of(input_lines(named.stdout)[0])[0]["expression"] == this_is_admin
    assert unnamed.returncode == 2, unnamed.stderr
    assert unnamed.stdout == ""
    with pytest.raises(TypeError) as plain:
        inspect.signature(shop.Till.total).bind(**json.loads(CART_SEED))
    reason = str(plain.value)
    assert unnamed.stderr.splitlines() == [
        f"args (self, discount) do not fit (this, discount): {reason}"
    ]


# point-at-a-class-or-one-of-its-methods-reports-a-constructor-that-raises
def test_reports_a_constructor_that_raises() -> None:
    result = run_pyct(f"{SHOP}::Cart.total", "--args", '{"self": {"owner": ""}, "discount": 1}')

    assert result.returncode == 0, result.stderr
    first, *solved = input_lines(result.stdout)
    empty = (
        line_of(shop.Cart.__init__, 'owner == ""'),
        ["==", ["[]", "self", "'owner'"], "''"],
        True,
    )
    assert empty in lines_expressions_and_sides(first), result.stdout
    detail = "building self: ValueError: no owner"
    assert first["failure"] == {"kind": "target_raised", "detail": detail}
    assert f"ended target raised: {detail}" in result.stderr.splitlines(), result.stderr
    in_total = body_lines(shop.Cart.total)
    built = [
        line
        for line in solved
        if self_of(line)["owner"] != ""
        and line["failure"] is None
        and any(fork["line"] in in_total for fork in forks_of(line))
    ]
    assert built, result.stdout


# point-at-a-class-or-one-of-its-methods-runs-a-class-as-its-constructor
def test_runs_a_class_as_its_constructor() -> None:
    result = run_pyct(f"{MODULE}::Cart", "--args", '{"owner": "ann"}')

    assert result.returncode == 0, result.stderr
    notice = (
        "Cart is a class, so each input constructs it; name a method as Cart.<method> to run it"
    )
    stderr = result.stderr.splitlines()
    assert stderr[:2] == [notice, 'seed {"owner": "ann"}'], result.stderr
    assert stderr.count(notice) == 1
    lines = input_lines(result.stdout)
    assert all("args" in line for line in lines), result.stdout
    [(file, covered)] = union_of(lines).items()
    assert body_lines(cart.Cart.__init__) <= set(covered)
    assert body_lines(cart.Cart.total) <= set(
        numbers_of(summary_line(result.stdout), "uncovered")[file]
    )


# point-at-a-class-or-one-of-its-methods-runs-other-kinds-of-method; Outer.Inner.check is
# point-at-a-class-or-one-of-its-methods-follows-a-nested-class
@pytest.mark.parametrize(
    ("name", "seed"),
    [
        pytest.param("Cart.from_text", {"text": "a"}, id="a-classmethod"),
        pytest.param("Cart.rate", {"x": 0}, id="a-staticmethod"),
        pytest.param("Outer.Inner.check", {"self": {}, "x": 0}, id="a-method-of-a-nested-class"),
        pytest.param("registry.lookup", {"key": "a"}, id="a-method-of-a-module-level-object"),
        pytest.param("handler", {"x": 0}, id="a-callable-object"),
    ],
)
def test_runs_other_kinds_of_method(name: str, seed: dict[str, object]) -> None:
    result = run_pyct(f"{MODULE}::{name}", "--args", json.dumps(seed))

    assert result.returncode == 0, result.stderr
    first, *solved = input_lines(result.stdout)
    [(line, expression, taken)] = lines_expressions_and_sides(first)
    assert first["args"] == seed
    assert taken is False
    other_side = [
        answer
        for answer in solved
        if (line, expression, True) in lines_expressions_and_sides(answer)
    ]
    assert other_side, result.stdout
    assert all(answer["failure"] is None for answer in other_side), result.stdout


# point-at-a-class-or-one-of-its-methods-takes-an-instance-as-self-through-run, in pyct's own
# process, where the caller's instance is the one an input would change were it not copied
def test_takes_an_instance_as_self_through_run(monkeypatch: pytest.MonkeyPatch) -> None:
    let_pyct_run_in_process(monkeypatch)
    target = load_target(f"{MODULE}::Cart.total")
    assert target.self_class is not None
    given = target.self_class(owner="ann")

    result = run(
        target, {"self": given, "discount": 5}, setup=Setup(isolation=Isolation.IN_PROCESS)
    )

    discounts = [record.args["discount"] for record in result.records]
    assert any(isinstance(discount, int) and discount > 10 for discount in discounts), discounts
    failures = [record.failure for record in result.records if record.failure is not None]
    assert all(failure.kind is not FailureKind.TARGET_RAISED for failure in failures), failures
    assert vars(given) == {"owner": "ann"}


# point-at-a-class-or-one-of-its-methods-reports-a-path-that-names-no-function
@pytest.mark.parametrize("name", ["Cart.totl", "Cart.count", "Cart.size"])
def test_reports_a_path_that_names_no_function(name: str) -> None:
    result = run_pyct(f"{MODULE}::{name}", "--args", '{"owner": "ann"}')

    assert result.stderr.splitlines() == [f"{MODULE} has no function {name}"]
    assert result.stdout == ""
    assert result.returncode == 1


# point-at-a-class-or-one-of-its-methods-refuses-a-malformed-path
@pytest.mark.parametrize("name", ["Cart.", ".total", "Cart..total"])
def test_refuses_a_malformed_path(name: str) -> None:
    spec = f"{MODULE}::{name}"

    result = run_pyct(spec, "--args", '{"owner": "ann"}')

    assert result.stderr.splitlines() == [f"target must be MODULE::FUNCTION, got {spec!r}"]
    assert result.stdout == ""
    assert result.returncode == 2


# a read along the path that raises other than AttributeError is refused (approved 2026-11-08, Q1)
def test_refuses_a_path_whose_read_raises() -> None:
    spec = "targets.load.raises_on_the_path::shelf.fetch"

    result = run_pyct(spec, "--args", '{"x": 0}')

    assert result.stderr.splitlines() == [f"cannot read {spec}: RuntimeError: the shelf is locked"]
    assert result.stdout == ""
    assert result.returncode == 1
