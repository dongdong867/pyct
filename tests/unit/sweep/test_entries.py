import importlib
import sys
import types
import typing

import pytest

from pyct.sweep.entries import (
    GENERATED,
    METHOD,
    Entry,
    Reading,
    entries_in,
    function_of,
    package_path,
    public_names,
)

SWEEP = "targets.sweep"


def read(module: str, package: str) -> Reading:
    return entries_in(importlib.import_module(module), module, package)


def entries(module: str, package: str) -> list[Entry]:
    reading = read(module, package)
    assert reading.unread is None
    return reading.entries


def test_a_function_is_named_by_the_module_whose_file_holds_it() -> None:
    shop = f"{SWEEP}.shop"
    assert entries(shop, shop) == [
        Entry(f"{shop}._parse", "parse_price", seed={"text": ""}),
        Entry(f"{shop}.prices", "total", seed={"n": 0}),
    ]
    assert entries(f"{shop}.catalog", shop) == [Entry(f"{shop}.prices", "total", seed={"n": 0})]


def test_code_outside_the_package_is_no_entry() -> None:
    catalog = f"{SWEEP}.shop.catalog"
    assert entries(catalog, catalog) == []


def test_only_functions_and_classes_of_the_package_are_entries() -> None:
    module = f"{SWEEP}.not_its_own"
    assert entries(module, module) == [Entry(module, "Cart", seed={"owner": ""})]


def test_a_name_that_loads_its_module_when_read_is_named_by_that_module() -> None:
    lazy = f"{SWEEP}.lazyall"
    assert entries(lazy, lazy) == [Entry(f"{lazy}._impl", "compute", seed={"n": 0})]


def test_all_decides_the_public_names() -> None:
    assert public_names(importlib.import_module(f"{SWEEP}.follows_all")) == ["a", "_b"]


def test_a_decorated_function_is_read_through_wrapped() -> None:
    wrapped = f"{SWEEP}.wrapped"
    assert entries(f"{wrapped}.prices", wrapped) == [
        Entry(f"{wrapped}._wrap", "logged", seed={"fn": 0}),
        Entry(f"{wrapped}.prices", "total", seed={"n": 0}),
        Entry(f"{wrapped}.prices", "fetch", seed={"key": 0}),
    ]


def test_a_class_is_its_constructor_and_its_own_methods_are_skipped() -> None:
    module = f"{SWEEP}.methods"
    found = entries(module, module)

    assert found[0] == Entry(module, "Cart", seed={"owner": ""})
    assert sorted(entry.name for entry in found[1:4]) == ["Cart.empty", "Cart.rate", "Cart.total"]
    assert found[4:] == [
        Entry(module, "Parser.parse", skip=METHOD),
        Entry(module, "Special", seed={"owner": ""}),
    ]
    assert {entry.skip for entry in found[1:4]} == {METHOD}


def test_generated_code_and_code_no_name_holds_are_skipped_where_found() -> None:
    generated = f"{SWEEP}.generated"
    assert entries(f"{generated}.api", generated) == [
        Entry(f"{generated}.factory", "make_parser", skip="no parameter to vary"),
        Entry(f"{generated}.api", "made", skip=GENERATED),
        Entry(f"{generated}.api", "parse", skip=f"no name in {generated}.factory holds it"),
    ]


def test_the_edges_of_what_a_name_holds() -> None:
    edges = "tests.unit.sweep.edges"
    reading = read(edges, "tests.unit.sweep")

    # the first public name that raised, in the words plain Python gives
    with pytest.raises(AttributeError) as plain:
        getattr(importlib.import_module(edges), "missing")  # noqa: B009 - a name __all__ lacks
    assert reading.unread == f"{edges}::missing: {plain.value!r}"
    assert reading.entries == [
        Entry(edges, "total", seed={"n": 0}),
        # an alias is the same entry, under the function's own name
        Entry(edges, "total", seed={"n": 0}),
        # the home holds it under another name only
        Entry(edges, "renamed", seed={"n": 0}),
        Entry(edges, "Built", skip="no name in tests.unit.sweep.factory holds it"),
        Entry(edges, "Moved.shift", skip=METHOD),
    ]


def test_function_of_reads_through_static_and_class_methods() -> None:
    def plain(n: int) -> int:
        return n

    assert function_of(staticmethod(plain)) is plain
    assert function_of(classmethod(plain)) is plain
    assert function_of(property(plain)) is None
    assert function_of(len) is None


def test_a_named_tuple_and_a_dataclass_are_named_by_their_own_file() -> None:
    # a named tuple's _make and _replace say they are its own, but their code is Python's
    module = f"{SWEEP}.tuples"
    assert entries(module, module) == [
        Entry(module, "Pair", seed={"a": 0, "b": 0}),
        Entry(module, "Point", seed={"x": 0, "y": 0}),
        Entry(module, "Span", seed={"start": 0, "end": 0}),
        Entry(module, "Span.length", skip=METHOD),
        Entry(module, "Box", seed={"width": 0, "label": "box"}),
    ]


def test_a_name_that_raises_when_asked_its_class_is_unread_and_the_rest_are_read() -> None:
    unread = f"{SWEEP}.unread"
    reading = read(unread, unread)

    raised = "RuntimeError('settings are not configured')"
    assert reading == Reading(
        [Entry(unread, "home", seed={"n": 0})], f"{unread}::settings: {raised}"
    )


class _LoadsWhenAsked(types.ModuleType):
    """A module whose file, when asked, would load it; here the asking is noted, and raises."""

    asked: list[str] = []

    @property
    def __file__(self) -> str:  # pyrefly: ignore[bad-override]
        _LoadsWhenAsked.asked.append(self.__name__)
        raise RuntimeError("loading failed")


def test_only_a_module_of_the_package_is_asked_its_file_and_its_raise_costs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = f"{SWEEP}.shop"
    monkeypatch.setattr(_LoadsWhenAsked, "asked", [])
    monkeypatch.setitem(sys.modules, "elsewhere", _LoadsWhenAsked("elsewhere"))
    monkeypatch.setitem(sys.modules, f"{shop}.lazy", _LoadsWhenAsked(f"{shop}.lazy"))

    assert [entry.name for entry in entries(shop, shop)] == ["parse_price", "total"]
    assert _LoadsWhenAsked.asked == [f"{shop}.lazy"]


def test_a_package_path_is_read_without_asking_the_module() -> None:
    lazy = importlib.import_module(f"{SWEEP}.unread.lazy")
    walk = importlib.import_module(f"{SWEEP}.walk")

    assert package_path(lazy) is None
    assert package_path(walk) == list(walk.__path__)
    # an object a module put in its own place may have no names of its own at all
    assert package_path(typing.cast(types.ModuleType, object())) is None
