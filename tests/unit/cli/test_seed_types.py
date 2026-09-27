import functools
import inspect
from collections.abc import Callable

import pytest

from pyct.binding.annotations import Check, Items
from pyct.binding.resolve import checked_annotations
from pyct.cli import UsageError, check_seed_types
from pyct.run.target import Target
from tests.unit.cli.declaring_decorator import declares_its_signature
from tests.unit.cli.inherited import (
    AgreeingBase,
    AgreeingCallingBase,
    AgreeingMakingBase,
    AgreeingMeta,
    Base,
    CallingBase,
    MakingBase,
    Meta,
)
from tests.unit.cli.wrapping_decorator import WrapsByHand, wrapped_elsewhere


def four_plain_types(s: str, n: int, x: float, b: bool) -> str:
    return f"{s}{n}{x}{b}"


def not_plain(s: str | None, xs: tuple[int, ...], c: Target) -> None:
    return None


def no_annotation(s) -> None:
    return None


def items(xs: list[int], cfg: dict[str, list[str]], bare: list, d: dict) -> None:
    return None


def items_as_text(xs: list[int]) -> None:
    return None


# the text, read in this module and in the wrapper's: each builds a list[int] of its own
items_as_text.__annotations__ = {"xs": "list[int]", "return": "None"}
wrapped_items = wrapped_elsewhere(items_as_text)


def stored_as_text(s: str, missing: object) -> None:
    return None


# what ``from __future__ import annotations`` leaves behind: the text, unresolved
stored_as_text.__annotations__ = {"s": "str", "missing": "Missing", "return": "None"}


class OnlyClaimsToBeStr:
    """An annotation object that compares equal to anything, ``str`` included."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def annotated_by_a_claim(s: object) -> None:
    return None


# an annotation is any object the source put there, and this one is not a type at all
annotated_by_a_claim.__annotations__ = {"s": OnlyClaimsToBeStr(), "return": None}


class Point:
    """A class target whose body annotation disagrees with its ``__init__``."""

    n: str

    def __init__(self, n: int) -> None:
        self.value = n


# the name the helper modules spell too, meaning a different plain type there
Number = int
# the name only this module spells
Here = int


class Named:
    """A class target whose ``__init__`` annotation is text naming a module alias."""

    def __init__(self, n: int) -> None:
        self.value = n


# what ``from __future__ import annotations`` leaves behind on a class target
Named.__init__.__annotations__ = {"n": "Number", "return": "None"}


class Inheriting(Base):
    """A class target whose ``__init__``, and its text, come from another module."""


class InheritingAgreeing(AgreeingBase):
    """A class target whose inherited ``__init__`` text only the base's module knows."""


class MakingElsewhere(MakingBase):
    """A class target with its own ``__init__`` and a ``__new__`` from another module."""

    def __init__(self, n: int, m: int) -> None:
        self.value = n


# the text on the target's own __init__; the __new__ beside it was written elsewhere
MakingElsewhere.__init__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}


class Making(MakingBase):
    """A class target read at a ``__new__``, and its text, from another module."""


class MakingAgreeing(AgreeingMakingBase):
    """A class target whose inherited ``__new__`` text only the base's module knows."""


class ViaMeta(metaclass=Meta):
    """A class target read through its metaclass's ``__call__``, written elsewhere."""

    def __init__(self) -> None:
        self.value = None


class ViaAgreeingMeta(metaclass=AgreeingMeta):
    """A class target whose metaclass ``__call__`` text only the metaclass's module knows."""


class Calling(CallingBase):
    """A callable object whose ``__call__``, and its text, come from another module."""


class CallingAgreeing(AgreeingCallingBase):
    """A callable object whose inherited ``__call__`` text only the base's module knows."""


calling = Calling()
calling_agreeing = CallingAgreeing()


def reads_here(n: int) -> None:
    return None


# a plain function's text, written against the one name only this module spells
reads_here.__annotations__ = {"n": "Here", "return": "None"}


def written_elsewhere(n: int, m: int) -> None:
    return None


written_elsewhere.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
# a plain function knows one namespace of its own; __module__ is the only way it names a second
written_elsewhere.__module__ = "tests.unit.cli.inherited"


class Counting:
    """The three kinds of method a module-level name can hold, bound or plain."""

    def counts(self, n: int, m: int) -> None:
        return None

    def counts_here(self, n: int) -> None:
        return None

    @classmethod
    def made(cls, n: int, m: int) -> None:
        return None

    @classmethod
    def made_here(cls, n: int) -> None:
        return None

    @staticmethod
    def helps(n: int, m: int) -> None:
        return None

    @staticmethod
    def helps_here(n: int) -> None:
        return None


# a method knows one namespace too, the one its function was written in
Counting.counts.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
Counting.counts.__module__ = "tests.unit.cli.inherited"
Counting.counts_here.__annotations__ = {"n": "Here", "return": "None"}
Counting.made.__func__.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
Counting.made.__func__.__module__ = "tests.unit.cli.inherited"
Counting.made_here.__func__.__annotations__ = {"n": "Here", "return": "None"}
Counting.helps.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
Counting.helps.__module__ = "tests.unit.cli.inherited"
Counting.helps_here.__annotations__ = {"n": "Here", "return": "None"}

# a bound method is reached through an instance, a classmethod and a staticmethod through
# the class; the seed fills what each one's signature leaves, so no self and no cls
bound_clashing = Counting().counts
bound_agreeing = Counting().counts_here
class_method_clashing = Counting.made
class_method_agreeing = Counting.made_here
static_clashing = Counting.helps
static_agreeing = Counting.helps_here


def counts(n: int, m: int) -> None:
    return None


# what ``from __future__ import annotations`` leaves behind, set before the decorator wraps it
counts.__annotations__ = {"n": "Number", "m": "int", "return": "None"}
wrapped_clashing = wrapped_elsewhere(counts)
by_hand_clashing = WrapsByHand(counts)
declared_clashing = declares_its_signature(counts, {"n": "Number", "m": "int"})
declared_agreeing = declares_its_signature(counts, {"n": "Elsewhere"})


def counts_here(n: int) -> None:
    return None


counts_here.__annotations__ = {"n": "Here", "return": "None"}
wrapped_agreeing = wrapped_elsewhere(counts_here)


def counts_items(n: list[int], m: int) -> None:
    return None


# a list of Number: a list of ints here and of strs in the wrapper's module
counts_items.__annotations__ = {"n": "list[Number]", "m": "int", "return": "None"}
wrapped_items_clashing = wrapped_elsewhere(counts_items)
by_hand_agreeing = WrapsByHand(counts_here)


def takes_two(first: int, n: int) -> None:
    return None


takes_two.__annotations__ = {"first": "int", "n": "Here", "return": "None"}
partial_agreeing = functools.partial(takes_two, 1)
partial_clashing = functools.partial(Inheriting)


def loops(n: int) -> None:
    return None


def loops_back(n: int) -> None:
    return None


# a __wrapped__ cycle, which only a declared signature above it lets anything reach
loops.__wrapped__ = loops_back  # pyrefly: ignore[missing-attribute]
loops_back.__wrapped__ = loops  # pyrefly: ignore[missing-attribute]
declared_over_a_cycle = declares_its_signature(loops, {"n": "Here"})


def target_for(fn: object) -> Target:
    """A Target around ``fn``: what the seed-type check reads, ``fn`` and its signature."""
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


def checked(fn: object) -> dict[str, Check]:
    """What the seed-type check reads of ``fn``, from the signature its loader read."""
    target = target_for(fn)
    return checked_annotations(target.signature, target.fn)


def test_checked_annotations_keeps_the_four_plain_types() -> None:
    assert checked(four_plain_types) == {
        "s": str,
        "n": int,
        "x": float,
        "b": bool,
    }


def test_checked_annotations_skips_the_return() -> None:
    assert "return" not in checked(four_plain_types)


def test_checked_annotations_skips_an_annotation_that_asks_nothing() -> None:
    assert checked(not_plain) == {}


def test_checked_annotations_keeps_a_list_or_dict_of_what_it_checks() -> None:
    assert checked(items) == {
        "xs": Items(list, int),
        "cfg": Items(dict, Items(list, str)),
        "bare": Items(list, None),
        "d": Items(dict, None),
    }


def test_checked_annotations_resolves_list_and_dict_text() -> None:
    # two namespaces build two list[int] objects from one text; they agree on what they ask
    assert checked(wrapped_items) == {"xs": Items(list, int)}


def test_checked_annotations_skips_a_parameter_with_no_annotation() -> None:
    assert checked(no_annotation) == {}


def test_checked_annotations_resolves_text_and_skips_only_what_it_cannot() -> None:
    # one bad name costs that parameter alone, not the whole function
    assert checked(stored_as_text) == {"s": str}


def test_checked_annotations_reads_a_class_target_at_its_init() -> None:
    # the class body says str, the parameter says int; the parameter is what a seed fills
    assert checked(Point) == {"n": int}


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        pytest.param(reads_here, {"n": int}, id="plain function"),
        pytest.param(bound_agreeing, {"n": int}, id="bound method"),
        pytest.param(class_method_agreeing, {"n": int}, id="class method"),
        pytest.param(static_agreeing, {"n": int}, id="static method"),
        pytest.param(wrapped_agreeing, {"n": int}, id="wraps decorator"),
        pytest.param(by_hand_agreeing, {"n": int}, id="wrapping object"),
        pytest.param(declared_agreeing, {"n": str}, id="declared signature"),
        # a class has no __globals__; its __init__'s are the names the text was written against
        pytest.param(Named, {"n": int}, id="own init"),
        pytest.param(InheritingAgreeing, {"n": str}, id="inherited init"),
        pytest.param(MakingAgreeing, {"n": str}, id="inherited new"),
        pytest.param(ViaAgreeingMeta, {"n": str}, id="metaclass call"),
        pytest.param(calling_agreeing, {"n": str}, id="inherited call"),
        pytest.param(partial_agreeing, {"n": int}, id="partial"),
    ],
)
def test_checked_annotations_keeps_text_one_module_knows_and_no_other_contradicts(
    target: Callable[..., object], expected: dict[str, type]
) -> None:
    # every module the text could have been written in reads it, and exactly one answers
    assert checked(target) == expected


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(written_elsewhere, id="plain function"),
        pytest.param(bound_clashing, id="bound method"),
        pytest.param(class_method_clashing, id="class method"),
        pytest.param(static_clashing, id="static method"),
        pytest.param(wrapped_clashing, id="wraps decorator"),
        pytest.param(wrapped_items_clashing, id="list of a name read two ways"),
        pytest.param(by_hand_clashing, id="wrapping object"),
        pytest.param(declared_clashing, id="declared signature"),
        pytest.param(MakingElsewhere, id="own init"),
        pytest.param(Inheriting, id="inherited init"),
        pytest.param(Making, id="inherited new"),
        pytest.param(ViaMeta, id="metaclass call"),
        pytest.param(calling, id="inherited call"),
        pytest.param(partial_clashing, id="partial"),
    ],
)
def test_checked_annotations_skips_text_two_modules_read_differently(
    target: Callable[..., object],
) -> None:
    # Number is an int in one candidate module and a str in the other, so n alone goes;
    # m, whose text both modules read as int, is still checked
    assert checked(target) == {"m": int}


def test_checked_annotations_ends_on_a_wrapped_cycle() -> None:
    # inspect stops at the declared signature and never walks the cycle below it, so
    # reading the namespaces is what meets it; a walk that did not stop would not end
    assert checked(declared_over_a_cycle) == {"n": int}


def test_checked_annotations_skips_an_annotation_that_only_claims_to_be_str() -> None:
    # equal to str is not str; keeping it would hand isinstance something that is not a type
    assert checked(annotated_by_a_claim) == {}


def test_check_seed_types_accepts_a_seed_that_fits_a_class_init() -> None:
    check_seed_types(target_for(Point), {"n": 5})


def test_check_seed_types_raises_one_line_per_contradiction() -> None:
    with pytest.raises(UsageError) as raised:
        check_seed_types(target_for(four_plain_types), {"s": 5, "n": "5", "x": 1, "b": True})

    assert str(raised.value) == 's must be a str, got 5\nn must be an int, got "5"'


def test_check_seed_types_accepts_a_matching_seed() -> None:
    check_seed_types(target_for(four_plain_types), {"s": "a", "n": 1, "x": 1.5, "b": True})


class ReadOnce:
    """A callable whose signature Python can read no more: a read raises.

    The test hands the seed check the signature the loader would have read
    before that, in a Target it builds itself.
    """

    @property
    def __signature__(self) -> inspect.Signature:
        raise RuntimeError("the signature was read a second time")

    def __call__(self, n: int) -> int:
        return n


def test_check_seed_types_reads_the_signature_the_loader_read() -> None:
    read_once = ReadOnce()
    loaded = inspect.Signature(
        [inspect.Parameter("n", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int)]
    )
    target = Target(spec="m::read_once", fn=read_once, file="m.py", signature=loaded)

    with pytest.raises(UsageError, match='n must be an int, got "5"'):
        check_seed_types(target, {"n": "5"})
