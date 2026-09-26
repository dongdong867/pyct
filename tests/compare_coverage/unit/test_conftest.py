"""The real legacy checkout the session builds: a failed build says why."""

import os
from pathlib import Path

import pytest

from tests.compare_coverage.conftest import build_legacy_checkout


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
