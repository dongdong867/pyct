"""The real legacy checkout the session builds once: a failed build says why."""

import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.compare_coverage.conftest import build_legacy_checkout, built_once


def test_a_failed_build_shows_what_uv_said(tmp_path: Path) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    uv = fake / "uv"
    uv.write_text("#!/bin/sh\necho 'error: no network to fetch coverage' >&2\nexit 2\n")
    uv.chmod(0o755)
    environment = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    checkout = tmp_path / "legacy"
    checkout.mkdir()

    with pytest.raises(pytest.fail.Exception, match="error: no network to fetch coverage"):
        build_legacy_checkout(checkout, environment)


def test_the_build_asks_uv_for_this_python(tmp_path: Path) -> None:
    # the standard library entries pin python, so legacy runs the checker's own release
    fake = tmp_path / "bin"
    fake.mkdir()
    uv = fake / "uv"
    uv.write_text(f'#!/bin/sh\necho "$@" > "{tmp_path / "args"}"\n')
    uv.chmod(0o755)
    environment = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    checkout = tmp_path / "legacy"
    checkout.mkdir()

    build_legacy_checkout(checkout, environment)

    args = (tmp_path / "args").read_text().split()
    assert args[args.index("--python") + 1] == platform.python_version()


def test_processes_sharing_a_folder_build_the_checkout_once(tmp_path: Path) -> None:
    # every worker of a parallel run asks for the checkout at once; the first builds it
    builds: list[Path] = []

    def build(checkout: Path) -> None:
        time.sleep(0.2)
        (checkout / "built").write_text("")
        builds.append(checkout)

    with ThreadPoolExecutor(4) as pool:
        given = list(pool.map(lambda _: built_once(tmp_path / "legacy", build), range(4)))

    assert builds == [tmp_path / "legacy"]
    assert given == [tmp_path / "legacy"] * 4
    assert (tmp_path / "legacy" / "built").exists()


def test_a_failed_build_is_tried_again_in_a_clean_folder(tmp_path: Path) -> None:
    def fails(checkout: Path) -> None:
        (checkout / "half").write_text("")
        pytest.fail("uv sync failed")

    with pytest.raises(pytest.fail.Exception, match="uv sync failed"):
        built_once(tmp_path / "legacy", fails)

    built_once(tmp_path / "legacy", lambda checkout: (checkout / "built").touch())

    assert sorted(path.name for path in (tmp_path / "legacy").iterdir()) == ["built"]
