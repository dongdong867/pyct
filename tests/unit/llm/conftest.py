from pathlib import Path

import pytest

from tests.acceptance.llm_stub import KEY_VARIABLES


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every worker these tests start inherits no real key, and SDKs that point at a local port
    nothing listens on, until a test points them at its stub. A recording goes to the test's
    own cache folder."""
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path / "cache"))
