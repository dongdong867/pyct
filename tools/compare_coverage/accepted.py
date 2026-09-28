"""The file of accepted differences: a row a person accepted passes until it changes.

``--accepted FILE`` opens with the limits it was made with, ``{budget, plateau,
solver_timeout}``, then holds one JSON record per line, ``{set, target, seed, status,
only_legacy, only_v2}``, sorted by set, target and seed, so a change to the file shows which
gaps moved (decision parity-gate-accepted-differences-pass-until-they-change). A record of a
failed row also holds ``failures``, each failed side's reason by side, and ``covered``, the
lines the side that ran covered, none when both failed. A reason is kept and compared in the
stable form ``reasons.py`` gives: memory addresses masked, paths written from the checkout
they are in, and the exception type and message as they were. A row keeps the text as given.

- A record is found by its target and seed. A row that matches its record, the same status,
  the same lines only each side covered and, for a failed row, the same reasons and the same
  lines covered by the side that ran, is ``accepted`` and passes whatever its status. One
  that does not is ``changed``, says what changed, and fails; a closed gap is a change.
- A row that ends on the budget can change with the budget, so a run is compared only with
  a file made with the same limits, with or without ``--accept``.
- Such a row can also change with the machine's load. A ``differs`` record may then hold
  ``varies``, ``{only_legacy, only_v2}``: the lines some accepted runs showed and others did
  not, beside ``only_legacy`` and ``only_v2``, which every one showed. A ``same`` or
  ``differs`` row matches it when each list of its lines holds the record's and nothing
  outside them and ``varies``. A line only legacy covered is one v2 misses: only a person
  puts it in ``varies``, with ``reason`` saying why it is timing, and it counts only in a run
  where a side ran its whole budget (decision
  compare-budget-bound-rows-legacy-range-only-at-the-budget). A record ``--accept`` keeps is
  written back as the file held it.
- ``--accept`` rewrites FILE after the last row, with the run's limits first: a row that
  matches its record keeps it as it was; a ``same`` or ``differs`` row where a side ran its
  whole budget, and whose lines only legacy covered fit the record, widens a ``differs``
  record it does not match to take in its lines only v2 covered, and says ``widened``; any
  other row this run produced replaces its record, a ``same``, ``left out`` or ``not listed``
  row leaving none. Records for entries this run did not run stay, and a record whose entry the
  list no longer holds is dropped.
"""

import json
import math
import os
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from tools.compare_coverage.entries import Origin
from tools.compare_coverage.ranges import (
    Varies,
    describe_range,
    lines_of,
    read_varies,
    span,
    varies_fields,
    within,
)
from tools.compare_coverage.reasons import stable_reason
from tools.compare_coverage.rows import Row, SideView, Status, budget_bound
from tools.compare_coverage.sides import Limits

type Roots = Mapping[Origin, Path]

type Key = tuple[str, str]

# rows with these statuses pass without a record, so they never leave one
PASSING = (Status.SAME, Status.LEFT_OUT)

FAILED = (Status.V2_FAILED, Status.LEGACY_FAILED, Status.BOTH_FAILED)

# rows whose lines a range can hold
COMPARED = (Status.SAME, Status.DIFFERS)


class RecordsError(Exception):
    """The accepted file cannot be read, or holds a line that is not a record."""


@dataclass(frozen=True)
class Record:
    """One accepted row, as the file holds it."""

    set: str
    target: str
    seed: Mapping[str, object]
    status: str
    only_legacy: tuple[int, ...]
    only_v2: tuple[int, ...]
    failures: Mapping[str, str] = field(default_factory=dict)
    covered: tuple[int, ...] = ()
    varies: Varies = Varies()
    # the line as the file held it, written back as it was while the record is kept
    line: str | None = field(default=None, compare=False)

    @property
    def key(self) -> Key:
        return key_of(self.target, self.seed)


@dataclass(frozen=True)
class Accepted:
    """The records of FILE, whether to rewrite it, and which keys the whole list still holds."""

    path: Path
    records: Mapping[Key, Record]
    accept: bool = False
    listed: frozenset[Key] = frozenset()


def key_of(target: str, seed: Mapping[str, object]) -> Key:
    """A record's key: its target and its seed as canonical JSON."""
    return target, json.dumps(seed, sort_keys=True)


def read_records(path: Path, accept: bool, limits: Limits) -> dict[Key, Record]:
    """The records in ``path``, made with ``limits``. With ``--accept``, a missing file has none."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if accept:
            return {}
        raise RecordsError(f"--accepted: cannot read {path}: no such file") from None
    except OSError as error:
        raise RecordsError(f"--accepted: cannot read {path}: {error.strerror}") from error
    first, *rest = _lines_in(text) or [""]
    made_with = _limits(first, path)
    if made_with != limits:
        raise RecordsError(
            f"--accepted: {path} was made with {describe(made_with)}; "
            f"this run has {describe(limits)}"
        )
    return _records(rest, path)


def _lines_in(text: str) -> list[str]:
    """The file's lines, split at newlines only.

    A record is written raw, so its seed or reason may hold U+2028, U+2029 or U+0085, which
    ``str.splitlines`` would split at; JSON escapes a newline, so a newline ends a record.
    Reading as text already turns ``\r\n`` into a newline.
    """
    lines = text.split("\n")
    return lines[:-1] if lines[-1] == "" else lines


def _limits(line: str, path: Path) -> Limits:
    """The limits the file's first line records."""
    refusal = RecordsError(
        f"--accepted: {path} line 1 does not record the limits it was made with: "
        '{"budget": SECONDS, "plateau": N, "solver_timeout": SECONDS}'
    )
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        raise refusal from None
    if not isinstance(raw, dict) or set(raw) != {"budget", "plateau", "solver_timeout"}:
        raise refusal
    if not all(type(value) in (int, float) for value in raw.values()):
        raise refusal
    return Limits(
        budget=raw["budget"], plateau=raw["plateau"], solver_timeout=raw["solver_timeout"]
    )


def describe(limits: Limits) -> str:
    return (
        f"budget {limits.budget:g} s, plateau {limits.plateau}, "
        f"solver timeout {limits.solver_timeout:g} s"
    )


def _records(lines: list[str], path: Path) -> dict[Key, Record]:
    """The records on the lines after the first, each read once."""
    records: dict[Key, Record] = {}
    numbers: dict[Key, int] = {}
    for number, line in enumerate(lines, 2):
        record = _record(line, f"{path} line {number}")
        if record.key in records:
            first = numbers[record.key]
            raise RecordsError(
                f"--accepted: {path} lines {first} and {number} record {record.target} "
                f"with the same seed; keep one"
            )
        records[record.key], numbers[record.key] = record, number
    return records


def check_writable(path: Path) -> None:
    """Refuse a file ``--accept`` could not write, before any target runs rather than after."""
    folder = path.parent
    if not folder.is_dir():
        raise RecordsError(f"--accepted: cannot write {path}: no folder {folder}")
    target = path if path.exists() else folder
    if not os.access(target, os.W_OK):
        raise RecordsError(f"--accepted: cannot write {path}: permission denied")


def _record(line: str, where: str) -> Record:
    try:
        raw = json.loads(line)
        failed = Status(raw["status"]) in FAILED
        record = Record(
            set=raw["set"],
            target=raw["target"],
            seed=raw["seed"],
            status=Status(raw["status"]).value,
            only_legacy=tuple(raw["only_legacy"]),
            only_v2=tuple(raw["only_v2"]),
            # a failed row's record needs both; any other record has neither
            failures=dict(raw["failures"]) if failed else {},
            covered=tuple(raw["covered"]) if failed else (),
            varies=read_varies(raw["varies"]) if "varies" in raw else Varies(),
            line=line,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RecordsError(f"--accepted: {where} is not a record: {error!r}") from error
    if not _well_formed(record):
        raise RecordsError(f"--accepted: {where} is not a record: {line}")
    return record


def _well_formed(record: Record) -> bool:
    varies = record.varies
    lines = [*record.only_legacy, *record.only_v2, *record.covered, *lines_of(varies)]
    reasons = [*record.failures, *record.failures.values()]
    texts = all(isinstance(text, str) for text in [record.set, record.target, *reasons])
    ints = isinstance(record.seed, dict) and all(type(n) is int for n in lines)
    return texts and ints and _range_fits(record)


def _range_fits(record: Record) -> bool:
    """A range sits only on a ``differs`` record and names no line its record always shows."""
    varies = record.varies
    if varies == Varies():
        return True
    apart = set(record.only_legacy).isdisjoint(varies.only_legacy) and set(
        record.only_v2
    ).isdisjoint(varies.only_v2)
    return record.status == Status.DIFFERS.value and apart


def mark(
    row: Row,
    records: Mapping[Key, Record],
    roots: Roots,
    budget: float = math.inf,
    accepting: bool = False,
) -> Row:
    """The row marked ``accepted`` or ``changed`` against its record, or as it was without one.

    ``roots`` are the checkouts this run's paths are under, for the row's stable reasons, and
    ``budget`` is the run's. Under ``--accept`` (``accepting``), a changed row also says
    whether ``--accept`` widens its record rather than replacing it.
    """
    if row.target is None or row.seed is None:
        return row
    record = records.get(key_of(row.target, row.seed))
    if record is None:
        return row
    change = _change(record, row, roots, budget_bound(row, budget))
    widened = accepting and change is not None and _widens(record, row, budget)
    record_mark = "accepted" if change is None else "changed"
    return replace(row, record=record_mark, change=change, widened=widened)


def _change(record: Record, row: Row, roots: Roots, bound: bool) -> str | None:
    """What differs between the record and the row, or ``None`` when they match.

    ``bound`` says a side of the row ran its whole budget; only then do the lines only legacy
    covered that the record's range holds count.
    """
    legacy_range, note = record.varies.only_legacy, ""
    if legacy_range and not bound:
        note = (
            f", and its range {_lines(legacy_range)} counts only when a side ran its whole budget"
        )
        legacy_range = ()
    sides = (
        ("only legacy", record.only_legacy, legacy_range, row.only_legacy, note),
        ("only v2", record.only_v2, record.varies.only_v2, row.only_v2, ""),
    )
    lines = [
        f"{name} was {describe_range(always, varies)}, now {_lines(now)}{note}"
        for name, always, varies, now, note in sides
        if not within(always, varies, now)
    ]
    # a range holds same and differs rows alike, so their status alone is no change
    ranged = record.varies != Varies() and row.status in COMPARED and not lines
    status = record.status != row.status.value and not ranged
    changes = [f"status was {record.status}, now {row.status.value}"] if status else []
    return "; ".join(changes + lines + _failure_changes(record, row, roots)) or None


def _failure_changes(record: Record, row: Row, roots: Roots) -> list[str]:
    """How a failed row's reasons and the lines of the side that ran moved from the record's."""
    failures, covered = _failures(row, roots), _covered(row)
    # the side that ran is the same one only while the status is
    ran = _ran(row) if record.status == row.status.value else "the side that ran"
    changes = [
        f"{side} failure was {_text(record.failures.get(side))}, now {_text(failures.get(side))}"
        for side in ("v2", "legacy")
        if record.failures.get(side) != failures.get(side)
    ]
    # the side that ran exists only while the record and the row both failed
    failed = Status(record.status) in FAILED and row.status in FAILED
    if failed and record.covered != covered:
        changes.append(f"{ran} covered was {_lines(record.covered)}, now {_lines(covered)}")
    return changes


def _sides(row: Row) -> list[tuple[str, SideView]]:
    return [(name, view) for name, view in (("v2", row.v2), ("legacy", row.legacy)) if view]


def _failures(row: Row, roots: Roots) -> dict[str, str]:
    """Each failed side's reason, by side, in its stable form."""
    return {
        name: stable_reason(view.failure, roots)
        for name, view in _sides(row)
        if view.failure is not None
    }


def _failed(row: Row) -> bool:
    return any(view.failure is not None for _, view in _sides(row))


def _ran(row: Row) -> str:
    """The side that ran while the other failed, or a phrase for a row with no such side."""
    ran = [name for name, view in _sides(row) if view.failure is None]
    return ran[0] if len(ran) == 1 and _failed(row) else "the side that ran"


def _covered(row: Row) -> tuple[int, ...]:
    """The lines the side that ran covered, when exactly one side failed; else none."""
    running = [view for _, view in _sides(row) if view.failure is None]
    return running[0].covered if len(running) == 1 and _failed(row) else ()


def _text(reason: str | None) -> str:
    return "none" if reason is None else repr(reason)


def _lines(lines: Sequence[int]) -> str:
    return ", ".join(map(str, lines)) or "none"


def passes(row: Row) -> bool:
    """A row with a record passes when accepted; one without, only as same or left out."""
    if row.record is not None:
        return row.record == "accepted"
    return row.status in PASSING


def rewritten(accepted: Accepted, rows: Iterable[Row], roots: Roots, budget: float) -> list[Record]:
    """The records ``--accept`` writes, sorted by set, target and seed.

    ``budget`` is the run's: a side that ran that long ran its whole budget.
    """
    records = {key: record for key, record in accepted.records.items() if key in accepted.listed}
    for row in rows:
        if row.target is None or row.seed is None:
            continue
        key = key_of(row.target, row.seed)
        record = _next_record(records.pop(key, None), row, roots, budget)
        if record is not None:
            records[key] = record
    return sorted(records.values(), key=lambda record: (record.set, *record.key))


def _next_record(old: Record | None, row: Row, roots: Roots, budget: float) -> Record | None:
    """The record ``--accept`` keeps for ``row``, as the module docstring says."""
    assert row.target is not None and row.seed is not None  # rewritten skips a file's row
    if old is not None and _change(old, row, roots, budget_bound(row, budget)) is None:
        return old
    if old is not None and _widens(old, row, budget):
        return _widened(old, row)
    if row.status in PASSING:
        return None
    return _record_of(row, row.target, row.seed, roots)


def _widens(old: Record, row: Row, budget: float) -> bool:
    """A budget-bound ``same`` or ``differs`` row whose lines only legacy covered fit ``old``."""
    lines = old.status == Status.DIFFERS.value and row.status in COMPARED
    legacy = within(old.only_legacy, old.varies.only_legacy, row.only_legacy)
    return lines and legacy and budget_bound(row, budget)


def _widened(old: Record, row: Row) -> Record:
    """``old`` with its range taking in the lines only v2 covered in the row.

    A line only v2 covered in one of the two and not in the other varies. The lines only
    legacy covered, the range's among them, stay as ``old`` has them.
    """
    always, varies = span(old.only_v2, old.varies.only_v2, row.only_v2)
    return replace(old, only_v2=always, varies=replace(old.varies, only_v2=varies), line=None)


def _record_of(row: Row, target: str, seed: Mapping[str, object], roots: Roots) -> Record:
    return Record(
        set=row.set,
        target=target,
        seed=seed,
        status=row.status.value,
        only_legacy=row.only_legacy,
        only_v2=row.only_v2,
        failures=_failures(row, roots),
        covered=_covered(row),
    )


def write_records(path: Path, limits: Limits, records: Collection[Record]) -> None:
    """The limits, then one record per line, keys in the order the module docstring gives."""
    made_with = {
        "budget": limits.budget,
        "plateau": limits.plateau,
        "solver_timeout": limits.solver_timeout,
    }
    lines = [json.dumps(made_with), *(_line(record) for record in records)]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _line(record: Record) -> str:
    """The record as the file held it, or, for a record this run made, its fields as JSON.

    A reason's text is written as it is, not escaped.
    """
    if record.line is not None:
        return record.line
    return json.dumps(_fields(record), ensure_ascii=False)


def _fields(record: Record) -> dict[str, object]:
    fields: dict[str, object] = {
        "set": record.set,
        "target": record.target,
        "seed": record.seed,
        "status": record.status,
        "only_legacy": list(record.only_legacy),
        "only_v2": list(record.only_v2),
    }
    if record.varies != Varies():
        fields["varies"] = varies_fields(record.varies)
    if Status(record.status) in FAILED:
        fields |= {"failures": dict(record.failures), "covered": list(record.covered)}
    return fields
