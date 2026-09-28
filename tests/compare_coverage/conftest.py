"""Legacy checkouts for the compare tool's tests: a stub one for exact answers, a real one.

``stub_checkout`` lays out a folder the checker takes for a legacy checkout: its
``.venv/bin/python`` runs this interpreter with the stub engine first on the path. The real
adapter and the real v2 side run against it, so a difference or a legacy failure a test
needs is exact, and does not move when a follow story closes a gap. It is not a git checkout,
so the checker keeps none of its results until a test commits it.

Every test's checker keeps legacy results in a folder of the test's own, never the user's.

``legacy_checkout`` is a real checkout of ``main`` with its own environment, made once per
session, however many workers a parallel run has: ``git archive main`` into pytest's temporary
folder, then ``uv sync`` with the ``realworld`` and ``library`` extras and this interpreter's
Python release. When ``PYCT_LEGACY_CHECKOUT`` names a checkout, that one is used instead.
"""

import fcntl
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STUB_ENGINE = Path(__file__).with_name("stub_engine.py")

# the first test that needs the real checkout builds it and the rest reuse it; a build that
# runs longer fails that test before its timeout marker, 180 s, would end the whole session
BUILD_SECONDS = 150

# the variables that name the caller's environment: uv would sync legacy's packages into the one
# UV_PROJECT_ENVIRONMENT names, and warns about VIRTUAL_ENV, rather than the checkout's own
CALLER_ENVIRONMENT = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")


@dataclass(frozen=True)
class StubCheckout:
    """A folder the checker takes for a legacy checkout, and the script its engine answers from."""

    path: Path

    def script(self, answers: Mapping[str, Mapping[str, object]]) -> None:
        (self.path / "stub.json").write_text(json.dumps(answers))

    def calls(self) -> list[dict[str, Any]]:
        calls = self.path / "calls.jsonl"
        if not calls.exists():
            return []
        return [json.loads(line) for line in calls.read_text().splitlines()]

    def commit(self) -> None:
        """Make the checkout a git checkout at one commit, its script included, as main is."""
        git = ("git", "-C", str(self.path), "-c", "user.name=t", "-c", "user.email=t@t")
        (self.path / ".gitignore").write_text("calls.jsonl\n")
        for command in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "stub")):
            subprocess.run([*git, *command], check=True, capture_output=True)

    def install(self, name: str, version: str, files: Mapping[str, str]) -> Path:
        """A library only this checkout's environment has, found before any other of the name.

        Gives the folder the library's modules sit in.
        """
        folder = self.path / "src"
        metadata = folder / f"{name}-{version}.dist-info" / "METADATA"
        metadata.parent.mkdir()
        metadata.write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        # the record says which files the library installed, so which modules it provides
        (metadata.parent / "RECORD").write_text("".join(f"{path},,\n" for path in files))
        for path, text in files.items():
            (folder / path).parent.mkdir(parents=True, exist_ok=True)
            (folder / path).write_text(text)
        return folder


@pytest.fixture(autouse=True)
def own_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The folder this test's checker keeps legacy results in, the default one for the test."""
    folder = tmp_path / "compare-cache"
    monkeypatch.setenv("PYCT_COMPARE_CACHE", str(folder))
    return folder


@pytest.fixture
def stub_checkout(tmp_path: Path) -> StubCheckout:
    checkout = tmp_path / "legacy"
    engine = checkout / "src" / "pyct"
    (engine / "engine").mkdir(parents=True)
    shutil.copy(STUB_ENGINE, engine / "__init__.py")
    (engine / "engine" / "__init__.py").write_text("")
    (engine / "engine" / "coverage_scope.py").write_text("from pyct import CoverageScope\n")
    python = checkout / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(f'#!/bin/sh\nPYTHONPATH="{checkout / "src"}" exec "{sys.executable}" "$@"\n')
    python.chmod(0o755)
    return StubCheckout(path=checkout)


@pytest.fixture(scope="session")
def legacy_checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    given = os.environ.get("PYCT_LEGACY_CHECKOUT")
    if given:
        return Path(given)
    # the session's temporary folder; a parallel run's workers each have one inside it
    folder = tmp_path_factory.getbasetemp()
    if os.environ.get("PYTEST_XDIST_WORKER"):
        folder = folder.parent
    return built_once(folder / "legacy", lambda path: build_legacy_checkout(path, os.environ))


def built_once(checkout: Path, build: Callable[[Path], None]) -> Path:
    """``checkout``, built by the first process that asks for it and reused by the rest.

    A lock beside it makes the others wait while one builds, and a marker beside it says the
    build finished. A build that failed leaves no marker, so the next process starts it again in
    an empty folder.
    """
    done = checkout.with_name(f"{checkout.name}.done")
    with checkout.with_name(f"{checkout.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not done.exists():
            shutil.rmtree(checkout, ignore_errors=True)
            checkout.mkdir()
            build(checkout)
            done.touch()
    return checkout


def build_legacy_checkout(checkout: Path, environment: Mapping[str, str]) -> None:
    """Extract main into ``checkout`` and install its own environment, whatever environment
    ``UV_PROJECT_ENVIRONMENT`` or ``VIRTUAL_ENV`` in ``environment`` names. A failure says what
    uv said."""
    own = {name: value for name, value in environment.items() if name not in CALLER_ENVIRONMENT}
    archive = subprocess.run(
        ["git", "archive", "main"], cwd=REPO_ROOT, capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(checkout)], input=archive.stdout, check=True)
    try:
        subprocess.run(
            [
                *("uv", "sync", "--frozen", "--no-dev", "--extra", "realworld"),
                *("--extra", "library", "--python", platform.python_version()),
            ],
            cwd=checkout,
            env=own,
            capture_output=True,
            text=True,
            check=True,
            timeout=BUILD_SECONDS,
        )
    except subprocess.CalledProcessError as error:
        pytest.fail(f"uv sync could not build a legacy checkout in {checkout}:\n{error.stderr}")
