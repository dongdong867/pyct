"""The classes a seeds ask lists: each top-level class of the target module's folder, read from
its file without importing it, the target's module first."""

import importlib
import sys
import time
import types
from pathlib import Path

import pytest

from pyct.run.class_listing import (
    CLASS_LIMIT,
    FILE_LIMIT,
    SHORTEST_CLASS,
    ClassListing,
    class_listing,
)
from pyct.run.target import load_target

GREET = "targets.llm.shop.greet"
MODELS = "targets.llm.shop.models"


def headings(listing: ClassListing) -> list[str]:
    return [line for line in listing.text.splitlines() if line.startswith("# ")]


def folder(tmp_path: Path, files: dict[str, str]) -> Path:
    """A folder ``listed`` under ``tmp_path`` holding ``files``, by name."""
    made = tmp_path / "listed"
    made.mkdir()
    for name, text in files.items():
        (made / name).write_text(text)
    return made


def loaded(monkeypatch: pytest.MonkeyPatch, name: str, file: Path) -> None:
    """A module ``name`` in ``sys.modules`` whose file is ``file``, its code never run."""
    module = types.ModuleType(name)
    module.__file__ = str(file)
    monkeypatch.setitem(sys.modules, name, module)


def test_the_folder_s_classes_are_listed_without_importing_their_module() -> None:
    load_target(f"{GREET}::greet")
    before = set(sys.modules)

    listing = class_listing(GREET)

    assert set(sys.modules) == before
    assert MODELS not in sys.modules
    assert headings(listing) == [
        f"# {MODELS}::{name}" for name in ("Customer", "Order", "Desk", "Till")
    ]
    assert listing.modules == frozenset({MODELS})
    assert (
        f"# {MODELS}::Customer\nclass Customer:\n    def __init__(self, name, age):\n"
        '        if age < 0:\n            raise ValueError("negative age")\n'
        "        self.name = name\n        self.age = age\n\n# "
    ) in listing.text


def test_a_class_shows_its_decorators_its_class_line_its_fields_and_its_init_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            "t.py": "from dataclasses import dataclass\nfrom typing import NamedTuple\n\n\n"
            '@dataclass(frozen=True)\nclass Point:\n    """A point."""\n\n    x: int\n'
            "    y: int = 0\n\n    def norm(self):\n        return 0\n\n\n"
            "class Pair(\n    NamedTuple,\n):\n    # the left\n    a: int\n\n\n"
            "class Box:\n    size = 3\n\n    @staticmethod\n    def make():\n        pass\n\n"
            "    def __init__(self, w):\n        self.w = w\n\n\n"
            "class Gap:\n\n    x: int\n",
        },
    )
    loaded(monkeypatch, "listed.t", made / "t.py")

    listing = class_listing("listed.t")

    assert listing.text == (
        "# listed.t::Point\n@dataclass(frozen=True)\nclass Point:\n    x: int\n    y: int = 0\n\n"
        "# listed.t::Pair\nclass Pair(\n    NamedTuple,\n):\n    # the left\n    a: int\n\n"
        "# listed.t::Box\nclass Box:\n    def __init__(self, w):\n        self.w = w\n\n"
        "# listed.t::Gap\nclass Gap:\n    x: int"
    )


def test_the_target_s_module_comes_first_then_the_others_by_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            "b.py": "class B:\n    pass\n",
            "t.py": "class T:\n    pass\n",
            "a.py": "class A:\n    pass\n\n\nclass A2:\n    pass\n",
            "__init__.py": "class I:\n    pass\n",
            "my-script.py": "class Unnamed:\n    pass\n",
        },
    )
    loaded(monkeypatch, "listed.t", made / "t.py")

    listing = class_listing("listed.t")

    assert headings(listing) == [
        "# listed.t::T",
        "# listed::I",
        "# listed.a::A",
        "# listed.a::A2",
        "# listed.b::B",
    ]
    assert listing.modules == frozenset({"listed", "listed.t", "listed.a", "listed.b"})


def test_a_package_s_main_is_left_out_since_importing_it_usually_runs_the_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {"t.py": "class T:\n    pass\n", "__main__.py": "class Main:\n    pass\n"},
    )
    loaded(monkeypatch, "listed.t", made / "t.py")

    listing = class_listing("listed.t")

    assert headings(listing) == ["# listed.t::T"]
    assert listing.modules == frozenset({"listed.t"})


def test_a_package_s_init_lists_the_package_s_own_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(tmp_path, {"__init__.py": "class I:\n    pass\n", "x.py": "class X:\n    pass\n"})
    loaded(monkeypatch, "listed", made / "__init__.py")

    assert headings(class_listing("listed")) == ["# listed::I", "# listed.x::X"]


def test_a_top_level_module_s_folder_lists_top_level_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {"solo.py": "class S:\n    pass\n", "other.py": "class O:\n    pass\n", "__init__.py": ""},
    )
    loaded(monkeypatch, "solo", made / "solo.py")

    assert headings(class_listing("solo")) == ["# solo::S", "# other::O"]


def test_a_class_goes_whole_or_not_at_all_and_a_later_one_may_still_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    long_init = "    def __init__(self):\n" + "        self.x = 1\n" * 40
    made = folder(
        tmp_path,
        {
            "t.py": "class T:\n    pass\n",
            "a.py": f"class Long:\n{long_init}",
            "b.py": "class B:\n    pass\n",
        },
    )
    loaded(monkeypatch, "listed.t", made / "t.py")
    first, _, last = class_listing("listed.t").text.split("\n\n")

    cut = class_listing("listed.t", limit=len(first) + 2 + len(last))

    assert cut.text == f"{first}\n\n{last}"
    assert cut.modules == frozenset({"listed.t", "listed.b"})


def test_a_file_that_does_not_parse_is_too_large_or_cannot_be_read_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            "t.py": "class T:\n    pass\n",
            "broken.py": "class Broken(:\n",
            # deep enough that the parser raises a RecursionError, and a MemoryError
            "deep.py": "class Deep:\n    pass\n\n\nx = " + "1+" * 50_000 + "1\n",
            "nested.py": "class Nested:\n    pass\n\n\nx = " + "-" * 50_000 + "1\n",
            "large.py": "class Large:\n    pass\n" + "#" * FILE_LIMIT + "\n",
            "locked.py": "class Locked:\n    pass\n",
        },
    )
    loaded(monkeypatch, "listed.t", made / "t.py")
    read_bytes = Path.read_bytes

    def locked(path: Path) -> bytes:
        if path.name == "locked.py":
            raise PermissionError(13, "Permission denied", str(path))
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", locked)

    listing = class_listing("listed.t")

    assert headings(listing) == ["# listed.t::T"]


def test_once_the_limit_is_full_the_later_files_are_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            "t.py": "class T:\n    pass\n",
            "a.py": "class A:\n    pass\n",
            "b.py": "class B:\n    pass\n",
        },
    )
    loaded(monkeypatch, "listed.t", made / "t.py")
    first = class_listing("listed.t").text.split("\n\n")[0]
    read: list[str] = []
    read_bytes = Path.read_bytes

    def reading(path: Path) -> bytes:
        read.append(path.name)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reading)

    listing = class_listing("listed.t", limit=len(first) + 2 + len("# listed.a::A\nclass A:") - 1)

    assert listing.text == first
    assert read == ["t.py"]


def test_a_file_whose_shortest_class_just_fits_the_room_left_is_read_and_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(tmp_path, {"t.py": "class T:\n    pass\n", "a.py": "class A:\n    pass\n"})
    loaded(monkeypatch, "listed.t", made / "t.py")
    first = class_listing("listed.t").text.split("\n\n")[0]
    shortest = SHORTEST_CLASS + len("listed.a")
    assert shortest == len("# listed.a::A\nclass A:")

    listing = class_listing("listed.t", limit=len(first) + 2 + shortest)

    assert headings(listing) == ["# listed.t::T", "# listed.a::A"]


def test_a_module_the_gate_refuses_is_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            "solo.py": "class S:\n    pass\n",
            "tabnanny.py": "class Nag:\n    pass\n",
            "__main__.py": "class Main:\n    pass\n",
        },
    )
    loaded(monkeypatch, "solo", made / "solo.py")

    assert headings(class_listing("solo")) == ["# solo::S"]


@pytest.mark.parametrize("name", ["os", "subprocess", "pluggy._manager", "pyct.run.setup"])
def test_a_target_in_a_library_or_in_pyct_gets_no_classes(name: str) -> None:
    importlib.import_module(name)

    assert class_listing(name) == ClassListing()


def test_a_module_that_is_not_loaded_or_has_no_file_lists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "listed_without_file", types.ModuleType("listed_without_file"))

    assert class_listing("listed_nowhere") == ClassListing()
    assert class_listing("listed_without_file") == ClassListing()


def test_a_folder_of_200_files_is_listed_within_two_seconds_and_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folder(
        tmp_path,
        {
            f"m{n:03}.py": f"class C{n}:\n    def __init__(self, x):\n        self.x = x\n"
            for n in range(200)
        },
    )
    loaded(monkeypatch, "listed.m000", made / "m000.py")
    started = time.monotonic()

    listing = class_listing("listed.m000")

    took = time.monotonic() - started
    # each class takes about 70 characters, so about 110 of the 200 fit
    assert 100 < len(headings(listing)) < 200
    assert len(listing.text) <= CLASS_LIMIT
    # the bound only catches a listing that reads far more than the folder
    assert took < 2, took
