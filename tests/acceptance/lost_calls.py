"""The fixtures and replies of the summarize-a-lost-call and track-a-value-through-a-call-summary
stories' criteria: `C`, its functions, `QUARTER`, `MOD`, `WRONG` and `CAP`, and how a test names a
loss site's place and its site."""

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
BOUNDED = "targets.summaries.calls::bounded"
DIVIDED = "targets.summaries.calls::divided"
EACH_DEDENTED = "targets.summaries.calls::each_dedented"
FORKED = "targets.summaries.calls::forked"
# the module `C` is, as a place names it
MODULE = "targets.summaries.calls"

QUARTER_CODE = 'def summary(n):\n    return {"answer": n % 4}'
MOD_CODE = 'def summary(n):\n    return {"answer": n * n % 10}'
# `QUARTER` and `MOD` of the criteria, and a formula that gives `n // 2`
QUARTER = code_reply(QUARTER_CODE)
MOD = code_reply(MOD_CODE)
HALF = code_reply('def summary(n):\n    return {"answer": n // 2}')
WRONG_CODE = 'def summary(n):\n    return {"answer": n * n}'
# `WRONG` and `CAP` of track-a-value-through-a-call-summary's criteria
WRONG = code_reply(WRONG_CODE)
CAP = code_reply(
    'def summary(n):\n    q = n % 4\n    if q > 2:\n        q = 2\n    return {"answer": q}'
)


def at(line: int, col: int) -> str:
    """A site in `C` as stderr writes a loss site's: ``file:line:col``."""
    return f"{C}:{line}:{col}"


def place(line: int, col: int) -> str:
    """A site in `C` as an ask names its place."""
    return f"{MODULE}:{line}:{col}"


def places(provider: FakeSummaries) -> list[str]:
    """The place of each ask the provider got, in order."""
    return [request.place for request in provider.requests]
