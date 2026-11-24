"""The fixtures and replies of the summarize-a-lost-call story's criteria: `C`, its functions,
`QUARTER` and `MOD`, and how a test names a loss site's place and its site."""

from __future__ import annotations

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.llm_summaries import FakeSummaries, code_reply

# `C` of the criteria
C = str(REPO_ROOT / "targets" / "summaries" / "calls.py")
SHIFTED = "targets.summaries.calls::shifted"
SQUARED = "targets.summaries.calls::squared"
BINNED = "targets.summaries.calls::binned"
DEEP = "targets.summaries.calls::deep"
LATE = "targets.summaries.calls::late"
MEASURED = "targets.summaries.calls::measured"
DEDENTED = "targets.summaries.calls::dedented"
WRAPPED = "targets.summaries.calls::wrapped"
MATCHED = "targets.summaries.calls::matched"
# the module `C` is, as a place names it
MODULE = "targets.summaries.calls"

QUARTER_CODE = 'def summary(n):\n    return {"answer": n % 4}'
MOD_CODE = 'def summary(n):\n    return {"answer": n * n % 10}'
# `QUARTER` and `MOD` of the criteria, and a formula that gives `n // 2`
QUARTER = code_reply(QUARTER_CODE)
MOD = code_reply(MOD_CODE)
HALF = code_reply('def summary(n):\n    return {"answer": n // 2}')


def at(line: int, col: int) -> str:
    """A site in `C` as stderr writes a loss site's: ``file:line:col``."""
    return f"{C}:{line}:{col}"


def place(line: int, col: int) -> str:
    """A site in `C` as an ask names its place."""
    return f"{MODULE}:{line}:{col}"


def places(provider: FakeSummaries) -> list[str]:
    """The place of each ask the provider got, in order."""
    return [request.place for request in provider.requests]
