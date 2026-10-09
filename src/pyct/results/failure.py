"""How a run of one input ended, when it did not return."""

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    """The six ways a call ends without returning. The values are the words on the line.

    ``crashed`` is a signal ending the input's process, which only a process
    of the input's own survives. ``too_long`` is an input whose path outgrew
    what pyct keeps for one input: more forks than a call keeps, wherever it
    runs, or a full journal in a process of its own. Like ``timeout``, it is
    the input's own ending, never pyct's.
    """

    TIMEOUT = "timeout"
    TARGET_RAISED = "target_raised"
    SYSTEM_EXIT = "system_exit"
    CRASHED = "crashed"
    TOO_LONG = "too_long"
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
