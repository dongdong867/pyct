"""Legacy results kept between runs: what a key holds, how a result is kept and read back."""

import hashlib
import json
from pathlib import Path

import pytest

from tools.compare_coverage.cache import (
    Cache,
    clear,
    default_folder,
    run_context,
    sources,
)
from tools.compare_coverage.sides import Installed, Limits, SideReport, SideRequest

LIMITS = {"budget": 5.0, "plateau": 5, "solver_timeout": 10}


def write(root: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def request(
    root: Path, target: str = "pkg.mod::f", seed: dict[str, object] | None = None
) -> SideRequest:
    return SideRequest(target, {"x": 0} if seed is None else seed, root, Limits(budget=5.0), 65.0)


def a_cache(tmp_path: Path, context: str = "c", refresh: bool = False) -> Cache:
    return Cache(folder=tmp_path / "cache", context=context, refresh_budget_spent=refresh)


def test_sources_are_the_module_its_packages_and_what_it_imports_from_the_root(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/mod.py": "import json\nfrom . import helper\nfrom pkg.deep import leaf\n",
            "pkg/helper.py": "from .deep.leaf import g\n",
            "pkg/deep/__init__.py": "",
            "pkg/deep/leaf.py": "def g():\n    import pkg.lazy\n",
            "pkg/lazy.py": "x = 1\n",
            "pkg/unrelated.py": "y = 2\n",
        },
    )

    found = sources("pkg.mod", tmp_path)

    assert found == {
        path: sha((tmp_path / path).read_text())
        for path in (
            "pkg/__init__.py",
            "pkg/mod.py",
            "pkg/helper.py",
            "pkg/deep/__init__.py",
            "pkg/deep/leaf.py",
            "pkg/lazy.py",
        )
    }


def test_a_file_that_does_not_parse_is_still_a_source(tmp_path: Path) -> None:
    write(tmp_path, {"broken.py": "def f(:\n"})

    assert sources("broken", tmp_path) == {"broken.py": sha("def f(:\n")}


def test_a_relative_import_past_the_top_package_names_nothing(tmp_path: Path) -> None:
    write(tmp_path, {"top.py": "from .. import far\nfrom . import near\n"})

    assert sources("top", tmp_path) == {"top.py": sha("from .. import far\nfrom . import near\n")}


def test_the_key_moves_with_everything_the_legacy_side_depends_on(tmp_path: Path) -> None:
    write(tmp_path, {"pkg/__init__.py": "", "pkg/mod.py": "def f(x):\n    return x\n"})
    cache = a_cache(tmp_path)
    base = cache.key(request(tmp_path), LIMITS)

    keys = {
        "seed": cache.key(request(tmp_path, seed={"x": 1}), LIMITS),
        "target": cache.key(request(tmp_path, target="pkg.mod::g"), LIMITS),
        "limits": cache.key(request(tmp_path), {**LIMITS, "budget": 30.0}),
        "context": a_cache(tmp_path, context="other").key(request(tmp_path), LIMITS),
    }
    (tmp_path / "pkg" / "mod.py").write_text("def f(x):\n    return -x\n")
    keys["source"] = cache.key(request(tmp_path), LIMITS)

    assert base not in keys.values()
    assert len(set(keys.values())) == len(keys)


def test_the_key_is_the_same_for_the_same_files_under_another_root(tmp_path: Path) -> None:
    files = {"pkg/__init__.py": "", "pkg/mod.py": "def f(x):\n    return x\n"}
    write(tmp_path / "a", files)
    write(tmp_path / "b", files)
    cache = a_cache(tmp_path)

    assert cache.key(request(tmp_path / "a"), LIMITS) == cache.key(request(tmp_path / "b"), LIMITS)


def test_an_installed_entry_is_keyed_by_its_library_not_its_empty_folder(tmp_path: Path) -> None:
    cache = a_cache(tmp_path)
    one = SideRequest("lib.mod::f", {}, tmp_path / "one", Limits(), 90.0, "lib")
    other = SideRequest("lib.mod::f", {}, tmp_path / "two", Limits(), 90.0, "lib")
    unnamed = SideRequest("lib.mod::f", {}, tmp_path / "two", Limits(), 90.0, None)

    assert cache.key(one, LIMITS) == cache.key(other, LIMITS) != cache.key(unnamed, LIMITS)


def test_a_kept_report_reads_back_reused_with_its_root_moved(tmp_path: Path) -> None:
    cache = a_cache(tmp_path)
    old, new = tmp_path / "old", tmp_path / "new"
    report = SideReport(
        file=str(old / "pkg" / "mod.py"),
        covered=frozenset({2, 3}),
        stopped="exhausted",
        inputs=4,
        failure=f"raised in {old}/pkg/mod.py",
        library=Installed(version="1.0", root="/site", provides=True),
    )

    cache.put("k", report, old)

    assert cache.get("k", new) == SideReport(
        file=str(new / "pkg" / "mod.py"),
        covered=frozenset({2, 3}),
        stopped="exhausted",
        inputs=4,
        failure=f"raised in {new}/pkg/mod.py",
        library=Installed(version="1.0", root="/site", provides=True),
        reused=True,
    )


def test_a_missing_or_unreadable_entry_is_not_kept(tmp_path: Path) -> None:
    cache = a_cache(tmp_path)
    cache.put("k", SideReport(file="/f.py"), tmp_path)
    (tmp_path / "cache" / "legacy" / "k.json").write_text("{not json")

    assert cache.get("missing", tmp_path) is None
    assert cache.get("k", tmp_path) is None


def test_a_budget_spent_report_is_kept_and_refreshed_when_asked(tmp_path: Path) -> None:
    spent = SideReport(file="/f.py", stopped="timeout", inputs=9)
    a_cache(tmp_path).put("spent", spent, tmp_path)
    a_cache(tmp_path).put("done", SideReport(file="/f.py", stopped="exhausted"), tmp_path)

    assert a_cache(tmp_path).get("spent", tmp_path) is not None
    assert a_cache(tmp_path, refresh=True).get("spent", tmp_path) is None
    assert a_cache(tmp_path, refresh=True).get("done", tmp_path) is not None


def test_clear_removes_every_kept_report_and_nothing_else(tmp_path: Path) -> None:
    cache = a_cache(tmp_path)
    cache.put("a", SideReport(), tmp_path)
    cache.put("b", SideReport(), tmp_path)
    other = tmp_path / "cache" / "notes.txt"
    other.write_text("mine")

    assert clear(tmp_path / "cache") == 2
    assert cache.get("a", tmp_path) is None
    assert other.read_text() == "mine"
    assert clear(tmp_path / "absent") == 0


def test_the_default_folder_is_the_variable_else_the_user_cache(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert default_folder({"PYCT_COMPARE_CACHE": "/c"}, home) == Path("/c")
    assert default_folder({"XDG_CACHE_HOME": "/x"}, home) == Path("/x/pyct/compare-coverage")
    assert default_folder({}, home) == home / ".cache" / "pyct" / "compare-coverage"


FACTS = {"commit": "abc", "changes": "d", "python": "3.12.1", "cvc5": "cvc5 1.3", "installed": ()}


@pytest.mark.parametrize("fact", sorted(FACTS))
def test_the_run_context_moves_with_each_fact(fact: str) -> None:
    changed = {**FACTS, fact: ("other",) if fact == "installed" else "other"}

    assert run_context(**changed) != run_context(**FACTS)  # type: ignore[arg-type]


def test_there_is_no_run_context_without_a_commit_or_its_changes() -> None:
    assert run_context(**{**FACTS, "commit": None}) is None  # type: ignore[arg-type]
    assert run_context(**{**FACTS, "changes": None}) is None  # type: ignore[arg-type]


def test_a_kept_report_is_one_json_file_named_by_its_key(tmp_path: Path) -> None:
    a_cache(tmp_path).put("k", SideReport(file="/f.py", covered=frozenset({1})), tmp_path)

    kept = json.loads((tmp_path / "cache" / "legacy" / "k.json").read_text())

    assert kept["report"]["covered"] == [1]
