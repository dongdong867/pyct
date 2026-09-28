"""Substituted code kept between runs: where, for which source, and what a failure costs."""

import os
import types
from pathlib import Path

import pytest

from pyct.intercept import cache
from pyct.intercept.cache import CACHE_VARIABLE, cache_folder, cached


class Module:
    """A module's source file, and a count of how often the cache read it and built it."""

    def __init__(self, folder: Path, text: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "m.py"
        self.path.write_text(text)
        self.reads = 0
        self.builds: list[str] = []

    def read(self) -> bytes:
        self.reads += 1
        return self.path.read_bytes()

    def build(self, source: bytes) -> types.CodeType:
        self.builds.append(source.decode())
        return compile(source, str(self.path), "exec")

    def code(self, root: Path) -> types.CodeType:
        return cached(root, str(self.path), self.read, self.build)


def entries(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.name != ".gitignore"]


@pytest.fixture
def settled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every file counts as long settled, as one written a while before the run is."""
    monkeypatch.setattr(cache, "_SETTLED_NS", -(10**18))


def test_the_folder_is_the_one_the_variable_names_or_pyct_cache_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CACHE_VARIABLE, raising=False)
    assert cache_folder() == tmp_path / ".pyct_cache"

    monkeypatch.setenv(CACHE_VARIABLE, "elsewhere")
    assert cache_folder() == tmp_path / "elsewhere"


@pytest.mark.usefixtures("settled")
def test_a_settled_unchanged_file_is_neither_read_nor_built_again(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")

    first = module.code(tmp_path / "cache")
    again = module.code(tmp_path / "cache")

    assert (module.reads, module.builds) == (1, ["x = 1"])
    assert first.co_consts == again.co_consts
    assert len(entries(tmp_path / "cache")) == 1
    # the folder keeps itself out of git
    assert (tmp_path / "cache" / ".gitignore").read_text().splitlines()[-1] == "*"


def test_a_file_changed_just_now_is_read_again_but_not_built_again(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")

    module.code(tmp_path / "cache")
    module.code(tmp_path / "cache")

    # its stat is not trusted yet, so its digest decides, and the digest is the same
    assert (module.reads, module.builds) == (2, ["x = 1"])


@pytest.mark.usefixtures("settled")
def test_an_edit_is_built_again_even_with_its_old_size_and_time(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")
    before = os.stat(module.path)

    module.path.write_text("x = 2")
    os.utime(module.path, ns=(before.st_atime_ns, before.st_mtime_ns))
    code = module.code(tmp_path / "cache")

    assert module.builds == ["x = 1", "x = 2"]
    assert 2 in code.co_consts
    assert len(entries(tmp_path / "cache")) == 1


@pytest.mark.usefixtures("settled")
def test_a_touched_file_with_the_same_source_is_kept_and_then_trusted(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")

    os.utime(module.path, ns=(1, 1))
    module.code(tmp_path / "cache")
    module.code(tmp_path / "cache")

    assert (module.reads, module.builds) == (2, ["x = 1"])


def test_another_module_path_has_its_own_entry(tmp_path: Path) -> None:
    for folder in ("a", "b"):
        Module(tmp_path / folder, "x = 1").code(tmp_path / "cache")

    assert len(entries(tmp_path / "cache")) == 2


@pytest.mark.usefixtures("settled")
@pytest.mark.parametrize("held", [b"", b"short", b"\0" * 80, b"head" * 20 + b"not marshal"])
def test_an_entry_that_cannot_be_read_back_is_a_miss(tmp_path: Path, held: bytes) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")
    (entry,) = entries(tmp_path / "cache")
    entry.write_bytes(held)

    code = module.code(tmp_path / "cache")

    assert module.builds == ["x = 1", "x = 1"]
    assert isinstance(code, types.CodeType)


@pytest.mark.usefixtures("settled")
def test_a_settled_entry_holding_no_code_is_a_miss(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")
    (entry,) = entries(tmp_path / "cache")
    head = entry.read_bytes()[: cache._HEAD.size]
    entry.write_bytes(head + b"\0garbage")

    module.code(tmp_path / "cache")

    assert module.builds == ["x = 1", "x = 1"]


def test_a_folder_that_cannot_be_made_keeps_nothing_and_says_so_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("a file where the folder would go")
    module = Module(tmp_path, "x = 1")

    for _ in range(2):
        code = module.code(blocked)

    assert isinstance(code, types.CodeType)
    assert module.builds == ["x = 1", "x = 1"]
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert str(blocked) in warnings[0].getMessage() and CACHE_VARIABLE in warnings[0].getMessage()


def test_a_folder_others_may_write_to_is_never_read_or_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    module = Module(tmp_path, "x = 1")

    module.code(shared)
    module.code(shared)

    assert module.builds == ["x = 1", "x = 1"]
    assert list(shared.iterdir()) == []
    assert "may write to it" in caplog.text


@pytest.mark.usefixtures("settled")
def test_an_entry_others_may_write_to_is_a_miss(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")
    (entry,) = entries(tmp_path / "cache")
    entry.chmod(0o666)

    module.code(tmp_path / "cache")

    assert module.builds == ["x = 1", "x = 1"]


@pytest.mark.usefixtures("settled")
def test_an_entry_that_opens_but_cannot_be_read_is_a_miss(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.code(tmp_path / "cache")
    (entry,) = entries(tmp_path / "cache")
    # a folder of this user's alone in the entry's place opens, and then refuses the read
    entry.unlink()
    entry.mkdir(mode=0o700)

    code = module.code(tmp_path / "cache")

    assert module.builds == ["x = 1", "x = 1"]
    assert isinstance(code, types.CodeType)


def test_the_folder_is_made_for_this_user_alone(tmp_path: Path) -> None:
    Module(tmp_path, "x = 1").code(tmp_path / "cache")

    assert (tmp_path / "cache").stat().st_mode & 0o777 == 0o700


def test_an_entry_that_cannot_be_put_in_place_leaves_no_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(source: str, target: str) -> None:
        raise PermissionError("refused")

    monkeypatch.setattr(cache.os, "replace", refused)

    Module(tmp_path, "x = 1").code(tmp_path / "cache")

    assert entries(tmp_path / "cache") == []


def test_a_source_that_cannot_be_read_raises_what_the_read_raises(tmp_path: Path) -> None:
    module = Module(tmp_path, "x = 1")
    module.path.unlink()

    with pytest.raises(FileNotFoundError):
        module.code(tmp_path / "cache")


def test_a_folder_that_fails_each_write_is_named_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refused(source: str, target: str) -> None:
        raise PermissionError(f"refused {source}")

    monkeypatch.setattr(cache.os, "replace", refused)

    for folder in ("a", "b", "c"):
        Module(tmp_path / folder, "x = 1").code(tmp_path / "cache")

    assert len([record for record in caplog.records if record.levelname == "WARNING"]) == 1
