"""The fixtures the acceptance tests of the LLM tools share."""

from collections.abc import Iterator

import pytest

from tests.acceptance.llm_stub import Stub, serving


@pytest.fixture
def stub() -> Iterator[Stub]:
    """A stand-in for both providers' APIs on a free localhost port, for the test's length."""
    with serving(Stub()) as running:
        yield running
