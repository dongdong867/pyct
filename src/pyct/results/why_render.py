"""A cause of uncovered lines as the summary line writes it, and as the stderr trace does."""

import dataclasses

from pyct.results.why import Condition, Reason, Tries, WhyEntry

# what each reason says after the lines on stderr, for the reasons that name nothing more
_SAID = {
    Reason.IMPORT: "import",
    Reason.HANDLER: "in a handler no raise reached",
    Reason.ENDED_BEFORE: "every input that got there ended before it",
}


def why_json(entry: WhyEntry) -> dict[str, object]:
    """``{"file", "lines", "reason"}``, then what the reason names: function, condition, tries."""
    payload: dict[str, object] = {
        "file": entry.file,
        "lines": list(entry.lines),
        "reason": entry.reason.value,
    }
    if entry.function is not None:
        payload["function"] = entry.function
    if entry.condition is not None:
        payload["condition"] = _condition(entry.condition)
    if entry.tries is not None:
        payload["tries"] = dataclasses.asdict(entry.tries)
    return payload


def why_line(entry: WhyEntry) -> str:
    """``why <lines> in <file>: <cause>``, the lines as the ``uncovered`` line writes them."""
    lines = ", ".join(str(line) for line in entry.lines)
    return f"why {lines} in {entry.file}: {_cause(entry)}"


def _cause(entry: WhyEntry) -> str:
    if entry.reason is Reason.NOT_CALLED:
        return f"{entry.function} not called"
    if entry.condition is None:
        return _SAID[entry.reason]
    never = _never(entry.condition)
    if entry.reason is Reason.NO_FORK:
        return f"{never}, no fork"
    counted = _counted(entry.tries or Tries())
    return f"{never}: {counted}" if counted else never


def _condition(condition: Condition) -> dict[str, object]:
    site = condition.site
    return {"file": site.file, "line": site.line, "col": site.col, "side": condition.side}


def _never(condition: Condition) -> str:
    site = condition.site
    side = "true" if condition.side else "false"
    return f"{site.file}:{site.line}:{site.col} never {side}"


def _counted(tries: Tries) -> str:
    """Each count above zero, in the key order, as ``1 unsat`` or ``2 not tried``."""
    counts = dataclasses.asdict(tries)
    return ", ".join(f"{n} {key.replace('_', ' ')}" for key, n in counts.items() if n)
