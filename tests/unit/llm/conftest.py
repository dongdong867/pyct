import pytest

from tests.acceptance.llm_stub import KEY_VARIABLES


@pytest.fixture(autouse=True)
def _no_real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every worker these tests start inherits no real key, and SDKs that point at a local port
    nothing listens on, until a test points them at its stub."""
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")
