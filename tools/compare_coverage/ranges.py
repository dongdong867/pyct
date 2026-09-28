"""A record's range: the lines its row showed in some accepted runs and not in others.

The accepted file keeps a range as a record's ``varies``, ``{only_legacy, only_v2}``, beside
``only_legacy`` and ``only_v2``, the lines every accepted run showed. A row's list of lines is
inside the range when it holds every line always shown and nothing past those and the range
(decision compare-budget-bound-rows-legacy-range-only-at-the-budget).
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Varies:
    """The lines a record's row showed in some accepted runs and not in others.

    ``--accept`` adds only lines only v2 covered. A line only legacy covered is one v2 misses,
    so only a person adds it, and ``reason`` says why it is timing and not a loss; such a line
    counts only in a run where a side ran its whole budget.
    """

    only_legacy: tuple[int, ...] = ()
    only_v2: tuple[int, ...] = ()
    reason: str | None = None


def read_varies(varies: object) -> Varies:
    """A record's ``varies`` as the file holds it.

    Refused with ``ValueError``: anything but two lists of lines, both lists empty, lines only
    legacy covered without a written reason, and a ``reason`` key without such lines.
    """
    if not isinstance(varies, dict) or set(varies) - {"reason"} != {"only_legacy", "only_v2"}:
        raise ValueError(f"varies must hold only_legacy and only_v2, got {varies!r}")
    legacy, v2 = varies["only_legacy"], varies["only_v2"]
    if not (isinstance(legacy, list) and isinstance(v2, list)) or not (legacy or v2):
        raise ValueError(f"varies must hold two lists of lines, not both empty: {varies!r}")
    reason = varies.get("reason")
    written = isinstance(reason, str) and bool(reason.strip())
    if bool(legacy) != written or ("reason" in varies and not written):
        raise ValueError(
            f"varies needs a written reason exactly when only legacy lines vary: {varies!r}"
        )
    return Varies(only_legacy=tuple(legacy), only_v2=tuple(v2), reason=reason if written else None)


def varies_fields(varies: Varies) -> dict[str, object]:
    """The range as the file holds it: both lists, then the reason when there is one."""
    fields: dict[str, object] = {
        "only_legacy": list(varies.only_legacy),
        "only_v2": list(varies.only_v2),
    }
    if varies.reason is not None:
        fields["reason"] = varies.reason
    return fields


def lines_of(varies: Varies) -> tuple[int, ...]:
    return (*varies.only_legacy, *varies.only_v2)


def within(always: Sequence[int], varies: Sequence[int], lines: Sequence[int]) -> bool:
    """The row's lines hold every line always shown and nothing past those and ``varies``."""
    return set(always) <= set(lines) <= set(always) | set(varies)


def describe_range(always: Sequence[int], varies: Sequence[int]) -> str:
    """A record's lines as a person reads them: ``5 and any of 4, 6``."""
    if not varies:
        return _text(always)
    if not always:
        return f"any of {_text(varies)}"
    return f"{_text(always)} and any of {_text(varies)}"


def span(
    always: Sequence[int], varies: Sequence[int], lines: Sequence[int]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The lines both always showed, and every other line either one showed."""
    both = set(always) & set(lines)
    seen = set(always) | set(varies) | set(lines)
    return tuple(sorted(both)), tuple(sorted(seen - both))


def _text(lines: Sequence[int]) -> str:
    return ", ".join(map(str, lines)) or "none"
