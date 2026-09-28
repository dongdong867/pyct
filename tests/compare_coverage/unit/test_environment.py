"""Where cvc5 is and what it says, the commit a checkout has out, and its changes."""

import subprocess
from pathlib import Path

import pytest

from tools.compare_coverage.environment import (
    SolverMissingError,
    changes,
    commit,
    cvc5_version,
    locate_cvc5,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def fake_cvc5(folder: Path, says: str, exit_code: int = 0) -> Path:
    cvc5 = folder / "cvc5"
    cvc5.write_text(f"#!/bin/sh\nprintf '{says}'\nexit {exit_code}\n")
    cvc5.chmod(0o755)
    return cvc5


def test_cvc5_is_found_on_the_given_path(tmp_path: Path) -> None:
    cvc5 = fake_cvc5(tmp_path, "cvc5 1.3.4\n")

    assert locate_cvc5({"PATH": f"/nowhere:{tmp_path}"}) == cvc5


def test_a_missing_cvc5_names_where_the_checker_looked(tmp_path: Path) -> None:
    with pytest.raises(SolverMissingError, match=rf"looked in: /nowhere, {tmp_path}\)"):
        locate_cvc5({"PATH": f"/nowhere::{tmp_path}"})
    with pytest.raises(SolverMissingError, match="nowhere, PATH is empty"):
        locate_cvc5({})


def test_the_version_is_the_first_line_cvc5_prints(tmp_path: Path) -> None:
    assert cvc5_version(fake_cvc5(tmp_path, "\\ncvc5 1.3.4 [git]\\ncompiled with\\n")) == (
        "cvc5 1.3.4 [git]"
    )


def test_a_cvc5_that_fails_or_says_nothing_has_no_version(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    assert cvc5_version(fake_cvc5(tmp_path / "a", "cvc5 1.3.4\\n", exit_code=1)) is None
    assert cvc5_version(fake_cvc5(tmp_path / "b", "")) is None
    assert cvc5_version(tmp_path / "missing") is None


def test_the_commit_is_head_of_a_checkout_root() -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )

    assert commit(REPO_ROOT) == head.stdout.strip()


def test_a_folder_that_is_no_checkout_root_has_no_commit(tmp_path: Path) -> None:
    assert commit(tmp_path) is None
    # a folder inside a checkout is not that checkout
    assert commit(REPO_ROOT / "targets") is None


def test_the_changes_move_with_a_tracked_file_and_not_with_an_untracked_one(
    tmp_path: Path,
) -> None:
    git = ("git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t")
    (tmp_path / "tracked.py").write_text("x = 1\n")
    for command in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "one")):
        subprocess.run([*git, *command], check=True, capture_output=True)
    clean = changes(tmp_path)
    (tmp_path / "untracked.py").write_text("y = 1\n")
    untracked = changes(tmp_path)
    (tmp_path / "tracked.py").write_text("x = 2\n")

    assert clean is not None
    assert untracked == clean
    assert changes(tmp_path) not in (None, clean)


def test_a_folder_git_cannot_read_has_no_changes(tmp_path: Path) -> None:
    assert changes(tmp_path) is None
