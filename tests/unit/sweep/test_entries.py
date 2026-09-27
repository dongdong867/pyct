import importlib

from pyct.sweep.entries import GENERATED, METHOD, Entry, entries_in, function_of, public_names

SWEEP = "targets.sweep"


def entries(module: str, package: str) -> list[Entry]:
    return entries_in(importlib.import_module(module), package)


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
    assert entries(edges, "tests.unit.sweep") == [
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
