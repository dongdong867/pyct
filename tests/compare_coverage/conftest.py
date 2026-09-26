"""Legacy checkouts for the compare tool's tests: a stub one for exact answers, a real one.

``stub_checkout`` lays out a folder the checker takes for a legacy checkout: its
``.venv/bin/python`` runs this interpreter with the stub engine first on the path. The real
adapter and the real v2 side run against it, so a difference or a legacy failure a test
needs is exact, and does not move when a follow story closes a gap.

``legacy_checkout`` is a real checkout of ``main`` with its own environment, made once per
session: ``git archive main`` into pytest's temporary folder, then ``uv sync``. When
``PYCT_LEGACY_CHECKOUT`` names a checkout, that one is used instead.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STUB_ENGINE = Path(__file__).with_name("stub_engine.py")

# the first test that needs the real checkout builds it and the rest reuse it; a build that
# runs longer fails that test before its timeout marker, 180 s, would end the whole session
BUILD_SECONDS = 150


@dataclass(frozen=True)
class StubCheckout:
    """A folder the checker takes for a legacy checkout, and the script its engine answers from."""

    path: Path

    def script(self, answers: Mapping[str, Mapping[str, object]]) -> None:
        (self.path / "stub.json").write_text(json.dumps(answers))

    def calls(self) -> list[dict[str, Any]]:
        calls = self.path / "calls.jsonl"
        return [json.loads(line) for line in calls.read_text().splitlines()]


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
    checkout = tmp_path_factory.mktemp("legacy")
    # the checkout's own environment, not this one: uv would warn and ignore it anyway
    build_legacy_checkout(checkout, {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    return checkout


def build_legacy_checkout(checkout: Path, environment: Mapping[str, str]) -> None:
    """Extract main into ``checkout`` and install its environment. A failure says what uv said."""
    archive = subprocess.run(
        ["git", "archive", "main"], cwd=REPO_ROOT, capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(checkout)], input=archive.stdout, check=True)
    try:
        subprocess.run(
            ["uv", "sync", "--frozen", "--no-dev"],
            cwd=checkout,
            env=dict(environment),
            capture_output=True,
            text=True,
            check=True,
            timeout=BUILD_SECONDS,
        )
    except subprocess.CalledProcessError as error:
        pytest.fail(f"uv sync could not build a legacy checkout in {checkout}:\n{error.stderr}")
