"""A cause of uncovered lines as the summary line writes it, and as the stderr trace does."""

import dataclasses

from pyct.results.causes import Condition, Reason, Source, SourceKind, Tries, WhyEntry

# what each reason says after the lines on stderr, for the reasons that name nothing more
_SAID = {
    Reason.IMPORT: "import",
    Reason.HANDLER: "in a handler no raise reached",
    Reason.ENDED_BEFORE: "every input that got there ended before it",
    Reason.NOT_WORKED_OUT: "not worked out before the deadline",
}


def why_json(entry: WhyEntry) -> dict[str, object]:
    """``{"file", "lines", "reason"}``, then what the reason names: function, condition, tries,
    sources."""
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
    if entry.sources is not None:
        payload["sources"] = [_source(source) for source in entry.sources]
    if entry.at_yield is not None:
        payload["yield"] = {"file": entry.file, "line": entry.at_yield}
    return payload


def why_line(entry: WhyEntry) -> str:
    """``why <lines> in <file>: <cause>``, the lines as the ``uncovered`` line writes them."""
    lines = ", ".join(str(line) for line in entry.lines)
    return f"why {lines} in {entry.file}: {_cause(entry)}"


def _cause(entry: WhyEntry) -> str:
    if entry.reason is Reason.NOT_CALLED:
        return f"{entry.function} not called"
    if entry.reason is Reason.SUSPENDED:
        return f"suspended at the yield on {entry.file}:{entry.at_yield}"
    if entry.condition is None:
        return _SAID[entry.reason]
    never = _never(entry.condition)
    if entry.reason is Reason.NO_FORK:
        return f"{never}, no fork{_from(entry.sources)}"
    counted = _counted(entry.tries or Tries())
    return f"{never}: {counted}" if counted else never


def _condition(condition: Condition) -> dict[str, object]:
    site = condition.site
    return {"file": site.file, "line": site.line, "col": site.col, "side": condition.side}


def _source(source: Source) -> dict[str, object]:
    """``{"kind", "name"}``, a lost one's ``"call"``, then the site."""
    payload: dict[str, object] = {"kind": source.kind.value, "name": source.name}
    if source.call is not None:
        payload["call"] = source.call
    site = source.site
    return {**payload, "file": site.file, "line": site.line, "col": site.col}


def _from(sources: tuple[Source, ...] | None) -> str:
    """Where the value came from, after the cause: each source, or that none was found."""
    if sources is None:
        return ""
    if not sources:
        return "; no source found"
    return "".join(f"; {_said(source)}" for source in sources)


def _said(source: Source) -> str:
    site = source.site
    if source.kind is SourceKind.LOOP:
        return f"{source.name} came from the loop at {site.file}:{site.line}"
    return f"{source.name} lost in {source.call} at {site.file}:{site.line}:{site.col}"


def _never(condition: Condition) -> str:
    site = condition.site
    side = "true" if condition.side else "false"
    return f"{site.file}:{site.line}:{site.col} never {side}"


def _counted(tries: Tries) -> str:
    """Each count above zero, in the key order, as ``1 unsat`` or ``2 not tried``."""
    counts = dataclasses.asdict(tries)
    return ", ".join(f"{n} {key.replace('_', ' ')}" for key, n in counts.items() if n)
