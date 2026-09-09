"""How a run of one input ended, when it did not return."""

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    """The four ways a call ends without returning. The values are the words on the line."""

    TIMEOUT = "timeout"
    TARGET_RAISED = "target_raised"
    SYSTEM_EXIT = "system_exit"
    PYCT_BUG = "pyct_bug"


@dataclass(frozen=True)
class Failure:
    """One failure: which kind, and one line a person can read."""

    kind: FailureKind
    detail: str
