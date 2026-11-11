"""``--llm`` and ``--llm-model`` refused as usage errors before any input runs.

Each run's base URLs point at a local port nothing listens on, and neither real key reaches
pyct, so no request can leave the machine.
"""

from pathlib import Path

import pytest

from tests.acceptance.harness import run_pyct
from tests.acceptance.llm_stub import KEY_VARIABLES, SEEDS_F, closed_port, llm_env

# `f(x: int)`: `if x == 1234:` guards `return 1`
F = SEEDS_F


# llm-switch-per-tool-unknown-tool
def test_a_tool_pyct_does_not_have_is_a_usage_error(tmp_path: Path) -> None:
    result = run_pyct(
        F,
        '{"x": 0}',
        "--llm",
        "seeds,magic",
        unset=KEY_VARIABLES,
        env=llm_env(tmp_path, closed_port()),
    )

    assert result.returncode == 2
    assert "'magic'" in result.stderr
    assert "seeds" in result.stderr
    assert result.stdout == ""


# llm-model-unknown-provider
@pytest.mark.parametrize("model", ["gemini:pro", "openai"])
def test_a_model_of_another_provider_or_none_is_a_usage_error(tmp_path: Path, model: str) -> None:
    result = run_pyct(
        F,
        '{"x": 0}',
        "--llm",
        "seeds",
        "--llm-model",
        model,
        unset=KEY_VARIABLES,
        env=llm_env(tmp_path, closed_port()),
    )

    assert result.returncode == 2
    assert "the provider anthropic or openai" in result.stderr
    assert result.stdout == ""
