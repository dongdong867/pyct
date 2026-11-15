"""The transform's version: the digest of pyct's files that decide what an entry holds, kept in
the cache folder while those files keep their settled stats."""

import hashlib
import os
from pathlib import Path

import pytest

from pyct.intercept import cache


class Rules:
    """Stand-in files for the ones the version digests, and a count of how often they were
    digested."""

    def __init__(self, folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        folder.mkdir()
        self.files = tuple(str(folder / f"rule{n}.py") for n in range(3))
        for n, file in enumerate(self.files):
            Path(file).write_text(f"rule = {n}\n")
        self.digests = 0
        real = cache._digest

        def counted(files: tuple[str, ...]) -> str:
            self.digests += 1
            return real(files)

        monkeypatch.setattr(cache, "_version_files", lambda: self.files)
        monkeypatch.setattr(cache, "_digest", counted)

    def expected(self) -> str:
        """The version the files make now, as the digest has always made it."""
        whole = b"".join(Path(file).read_bytes() for file in self.files)
        return hashlib.sha256(whole).hexdigest()[:16]


@pytest.fixture
def rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rules:
    return Rules(tmp_path / "rules", monkeypatch)


@pytest.fixture
def settled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every file counts as long settled, as one written a while before the run is."""
    monkeypatch.setattr(cache, "_SETTLED_NS", -(10**18))


def kept(root: Path) -> Path:
    return root / "substituted" / "version"


def test_the_version_is_the_digest_of_pyct_s_files_read_in_order() -> None:
    # the value an existing cache folder is named by: a change here orphans every user's cache
    files = cache._version_files()
    whole = b"".join(Path(file).read_bytes() for file in files)

    assert cache._digest(files) == hashlib.sha256(whole).hexdigest()[:16]


@pytest.mark.usefixtures("settled")
def test_a_kept_version_is_used_while_every_file_keeps_its_stat(
    tmp_path: Path, rules: Rules
) -> None:
    first = cache._version(tmp_path)
    again = cache._version(tmp_path)

    assert first == again == rules.expected()
    assert rules.digests == 1
    assert kept(tmp_path).stat().st_mode & 0o077 == 0


@pytest.mark.usefixtures("settled")
def test_an_edit_with_the_old_size_and_time_makes_a_new_version_and_keeps_it(
    tmp_path: Path, rules: Rules
) -> None:
    old = cache._version(tmp_path)
    before = os.stat(rules.files[1])
    Path(rules.files[1]).write_text("rule = 9\n")
    os.utime(rules.files[1], ns=(before.st_atime_ns, before.st_mtime_ns))

    new = cache._version(tmp_path)
    again = cache._version(tmp_path)

    assert old != new == again == rules.expected()
    assert rules.digests == 2


@pytest.mark.usefixtures("settled")
def test_a_file_of_another_size_makes_a_new_version(tmp_path: Path, rules: Rules) -> None:
    old = cache._version(tmp_path)
    Path(rules.files[0]).write_text("rule = 'longer'\n")

    assert old != cache._version(tmp_path) == rules.expected()


@pytest.mark.usefixtures("settled")
def test_a_touched_file_is_digested_again_to_the_same_version(tmp_path: Path, rules: Rules) -> None:
    old = cache._version(tmp_path)
    os.utime(rules.files[2], ns=(1, 1))

    assert cache._version(tmp_path) == old == rules.expected()
    assert rules.digests == 2


def test_a_version_of_files_changed_just_now_is_not_kept(
    tmp_path: Path, rules: Rules, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a clock too coarse to tell an edit made now from the last one: the stat stays the same
    now = os.stat(rules.files[0]).st_ctime_ns
    monkeypatch.setattr(cache, "_stat", lambda path: (now, now, 10, 1, 1))
    cache._version(tmp_path)
    Path(rules.files[0]).write_text("rule = 7\n")

    assert cache._version(tmp_path) == rules.expected()
    assert not kept(tmp_path).exists()


@pytest.mark.usefixtures("settled")
@pytest.mark.parametrize(
    "held",
    [b"", b"short", b"\0" * 48, b"\0" * 49, b"x" * 47],
    ids=["empty", "short", "another stat", "too long", "cut short"],
)
def test_a_kept_version_that_cannot_be_read_back_is_digested_again_and_kept(
    tmp_path: Path, rules: Rules, held: bytes
) -> None:
    cache._version(tmp_path)
    kept(tmp_path).write_bytes(held)

    first = cache._version(tmp_path)
    again = cache._version(tmp_path)

    assert first == again == rules.expected()
    assert rules.digests == 2


@pytest.mark.usefixtures("settled")
def test_a_kept_version_that_is_not_a_digest_is_never_a_folder_name(
    tmp_path: Path, rules: Rules
) -> None:
    cache._version(tmp_path)
    head = kept(tmp_path).read_bytes()[:32]
    kept(tmp_path).write_bytes(head + b"../../../../etc/")

    assert cache._version(tmp_path) == rules.expected()


@pytest.mark.usefixtures("settled")
def test_a_kept_version_others_may_write_to_is_not_read(tmp_path: Path, rules: Rules) -> None:
    cache._version(tmp_path)
    kept(tmp_path).chmod(0o666)

    assert cache._version(tmp_path) == rules.expected()
    assert rules.digests == 2


@pytest.mark.usefixtures("settled")
def test_a_version_that_cannot_be_put_in_place_leaves_no_file_behind(
    tmp_path: Path, rules: Rules, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(source: str, target: str) -> None:
        raise PermissionError("refused")

    monkeypatch.setattr(cache.os, "replace", refused)

    assert cache._version(tmp_path) == rules.expected()
    assert [path.name for path in kept(tmp_path).parent.iterdir()] == []


@pytest.mark.usefixtures("settled")
def test_a_folder_that_cannot_be_written_still_gives_the_version_and_says_so_once(
    tmp_path: Path, rules: Rules, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "cache"
    root.mkdir(mode=0o500)
    try:
        versions = {cache._version(root) for _ in range(2)}
    finally:
        root.chmod(0o700)

    assert versions == {rules.expected()}
    assert rules.digests == 2
    assert len([record for record in caplog.records if record.levelname == "WARNING"]) == 1
