"""How a run of one input ended, when it did not return."""

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    """The five ways a call ends without returning. The values are the words on the line.

    ``crashed`` is a signal ending the input's process, which only a process
    of the input's own survives.
    """

    TIMEOUT = "timeout"
    TARGET_RAISED = "target_raised"
    SYSTEM_EXIT = "system_exit"
    CRASHED = "crashed"
    PYCT_BUG = "pyct_bug"


@dataclass(frozen=True)
class Failure:
    """One failure: which kind, and one line a person can read.

    ``traceback`` is the whole formatted traceback, kept only for a pyct bug,
    where the frames are what a person needs to fix pyct. It goes to stderr;
    the JSON line stays the kind and the detail.
    """

    kind: FailureKind
    detail: str
    traceback: str | None = None
