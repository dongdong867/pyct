"""The lines that end stderr's run summary with ``--llm``: the counts, then the recording."""

from pyct.cli.llm import counts_line
from pyct.results.llm_asks import LlmUse


# llm-tokens-reported-summary-and-stderr
def test_the_counts_line_says_the_asks_the_tokens_and_the_wait() -> None:
    use = LlmUse(
        "openai:gpt-6-luna", ("seeds",), asks=1, tokens_in=1200, tokens_out=300, seconds=12.3
    )

    assert counts_line(use) == (
        "llm: 1 asks, 0 replayed, 0 skipped, 1200 tokens in, 300 out, 12.3 s waiting"
    )
