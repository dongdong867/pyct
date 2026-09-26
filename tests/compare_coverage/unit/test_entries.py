"""The target list: loading it, choosing entries by flag, and finding files no entry names."""

import json
from pathlib import Path

import pytest

from tools.compare_coverage.entries import (
    LIST_FILE,
    Entry,
    ListError,
    Origin,
    SelectionError,
    SetSpec,
    TargetList,
    Unlisted,
    entry_file,
    load_list,
    parse_list,
    unlisted_files,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

SETS = {"one": {"origin": "v2", "scan": "targets"}, "two": {"origin": "legacy"}}


def a_list(*entries: dict[str, object]) -> TargetList:
    return parse_list({"sets": SETS, "entries": list(entries)})


def test_every_file_under_targets_has_an_entry() -> None:
    # a story that adds a target learns here, in the normal suite, that it needs an entry
    target_list = load_list(LIST_FILE)

    assert unlisted_files(target_list, ["v2"], {Origin.V2: REPO_ROOT}) == ()


def test_the_committed_list_names_its_sets_and_where_they_live() -> None:
    target_list = load_list(LIST_FILE)

    assert target_list.sets == {
        "v2": SetSpec("v2", Origin.V2, "targets"),
        "fixtures": SetSpec("fixtures", Origin.LEGACY, "tests/acceptance/fixtures"),
    }


def test_an_entry_names_its_target_and_seed() -> None:
    target_list = a_list({"set": "one", "target": "pkg.mod::f", "seed": {"x": 0}})

    (entry,) = target_list.entries
    assert entry == Entry(set="one", module="pkg.mod", name="f", seed={"x": 0})
    assert entry.target == "pkg.mod::f"


def test_a_left_out_entry_names_its_module_and_reason() -> None:
    target_list = a_list({"set": "two", "module": "pkg.mod", "left_out": "fails to import"})

    (entry,) = target_list.entries
    assert entry == Entry(set="two", module="pkg.mod", left_out="fails to import")
    assert entry.target is None


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], 'a JSON object with "sets" and "entries"'),
        ({"sets": {}}, 'a JSON object with "sets" and "entries"'),
        ({"sets": {"s": {"origin": "elsewhere"}}, "entries": []}, "set s: origin must be"),
        ({"sets": {"s": {}}, "entries": []}, "set s: origin must be"),
        ({"sets": {"s": {"origin": "v2", "scan": 3}}, "entries": []}, "set s: scan must be"),
        ({"sets": SETS, "entries": [{"set": "three"}]}, "entry 1: set must name"),
        ({"sets": SETS, "entries": [7]}, "entry 1: set must name"),
        ({"sets": SETS, "entries": [{"set": ["one"]}]}, "entry 1: set must name"),
        ({"sets": SETS, "entries": [{"set": "one", "target": "mod", "seed": {}}]}, "MODULE::NAME"),
        (
            {"sets": SETS, "entries": [{"set": "one", "target": "a b::f", "seed": {}}]},
            "MODULE::NAME",
        ),
        ({"sets": SETS, "entries": [{"set": "one", "target": 5, "seed": {}}]}, "MODULE::NAME"),
        ({"sets": SETS, "entries": [{"set": "one", "target": "m::f", "seed": []}]}, "JSON object"),
        ({"sets": SETS, "entries": [{"set": "one", "target": "m::f"}]}, "JSON object"),
        ({"sets": SETS, "entries": [{"set": "one", "module": "m", "left_out": ""}]}, "a reason"),
        ({"sets": SETS, "entries": [{"set": "one", "module": "m b", "left_out": "r"}]}, "module"),
    ],
)
def test_a_malformed_list_is_refused_naming_what_is_wrong(document: object, message: str) -> None:
    with pytest.raises(ListError, match=message):
        parse_list(document)


def test_a_list_that_is_not_json_is_refused_naming_the_file(tmp_path: Path) -> None:
    broken = tmp_path / "targets.json"
    broken.write_text("{")

    with pytest.raises(ListError, match=rf"{broken}"):
        load_list(broken)


def test_a_missing_list_is_refused_naming_the_file(tmp_path: Path) -> None:
    with pytest.raises(ListError, match="cannot read"):
        load_list(tmp_path / "missing.json")


def test_a_list_file_holds_one_json_document(tmp_path: Path) -> None:
    file = tmp_path / "targets.json"
    file.write_text(json.dumps({"sets": SETS, "entries": []}))

    assert load_list(file).entries == ()


def test_no_flag_selects_every_entry_and_scans_every_set() -> None:
    target_list = a_list(
        {"set": "one", "target": "m::f", "seed": {}},
        {"set": "two", "target": "n::g", "seed": {}},
    )

    assert target_list.select([], []) == target_list.entries
    assert target_list.scanned([], []) == ("one", "two")


def test_sets_and_targets_select_their_union_in_list_order() -> None:
    target_list = a_list(
        {"set": "one", "target": "m::f", "seed": {}},
        {"set": "one", "target": "m::g", "seed": {}},
        {"set": "two", "target": "n::g", "seed": {}},
        {"set": "two", "module": "n.left", "left_out": "why"},
    )

    selected = target_list.select(["two"], ["m::f"])

    assert [entry.target for entry in selected] == ["m::f", "n::g", None]
    assert target_list.scanned(["two"], ["m::f"]) == ("two",)


def test_a_target_alone_scans_no_set() -> None:
    target_list = a_list({"set": "one", "target": "m::f", "seed": {}})

    assert target_list.scanned([], ["m::f"]) == ()


def test_an_unknown_set_is_refused_naming_the_flag_and_the_sets() -> None:
    target_list = a_list()

    with pytest.raises(SelectionError, match="--set: no set named 'three'; the sets are one, two"):
        target_list.select(["three"], [])


def test_an_unknown_target_is_refused_naming_the_flag() -> None:
    target_list = a_list({"set": "one", "target": "m::f", "seed": {}})

    with pytest.raises(SelectionError, match="--target: no entry runs 'm::g'"):
        target_list.select([], ["m::g"])


def test_a_file_no_entry_names_is_unlisted(tmp_path: Path) -> None:
    (tmp_path / "targets" / "sub").mkdir(parents=True)
    for name in ("listed.py", "left.py", "__init__.py", "sub/unlisted.py", "notes.txt"):
        (tmp_path / "targets" / name).write_text("")
    target_list = a_list(
        {"set": "one", "target": "targets.listed::f", "seed": {}},
        {"set": "one", "module": "targets.left", "left_out": "why"},
        # an entry of another set does not list a file of this one
        {"set": "two", "target": "targets.sub.unlisted::f", "seed": {}},
    )

    found = unlisted_files(target_list, ["one", "two"], {Origin.V2: tmp_path})

    assert found == (Unlisted(set="one", file=tmp_path / "targets" / "sub" / "unlisted.py"),)


def test_a_module_is_its_file_or_its_package(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")

    assert entry_file("a.b", tmp_path) == tmp_path / "a" / "b.py"
    assert entry_file("pkg", tmp_path) == tmp_path / "pkg" / "__init__.py"
