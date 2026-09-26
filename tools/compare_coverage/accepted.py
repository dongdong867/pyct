"""The file of accepted differences: a row a person accepted passes until it changes.

``--accepted FILE`` holds one JSON record per line, ``{set, target, seed, status,
only_legacy, only_v2}``, sorted by set, target and seed, so a change to the file shows which
gaps moved (decision parity-gate-accepted-differences-pass-until-they-change).

- A record is found by its target and seed. A row that matches its record, the same status
  and the same lines only each side covered, is ``accepted`` and passes whatever its status.
  One that does not is ``changed``, says what changed, and fails; a closed gap is a change.
- ``--accept`` rewrites FILE after the last row: each row this run produced replaces its
  record, a ``same``, ``left out`` or ``not listed`` row leaves none, records for entries
  this run did not run stay, and a record whose entry the list no longer holds is dropped.
"""

import json
import os
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from tools.compare_coverage.rows import Row, Status

type Key = tuple[str, str]

# rows with these statuses pass without a record, so they never leave one
PASSING = (Status.SAME, Status.LEFT_OUT)


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


def read_records(path: Path, accept: bool) -> dict[Key, Record]:
    """The records in ``path``. A missing file holds none when ``--accept`` will write it."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if accept:
            return {}
        raise RecordsError(f"--accepted: cannot read {path}: no such file") from None
    except OSError as error:
        raise RecordsError(f"--accepted: cannot read {path}: {error.strerror}") from error
    records: dict[Key, Record] = {}
    lines: dict[Key, int] = {}
    for number, line in enumerate(text.splitlines(), 1):
        record = _record(line, f"{path} line {number}")
        if record.key in records:
            first = lines[record.key]
            raise RecordsError(
                f"--accepted: {path} lines {first} and {number} record {record.target} "
                f"with the same seed; keep one"
            )
        records[record.key], lines[record.key] = record, number
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
        record = Record(
            set=raw["set"],
            target=raw["target"],
            seed=raw["seed"],
            status=Status(raw["status"]).value,
            only_legacy=tuple(raw["only_legacy"]),
            only_v2=tuple(raw["only_v2"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RecordsError(f"--accepted: {where} is not a record: {error!r}") from error
    if not _well_formed(record):
        raise RecordsError(f"--accepted: {where} is not a record: {line}")
    return record


def _well_formed(record: Record) -> bool:
    lines = [*record.only_legacy, *record.only_v2]
    texts = isinstance(record.set, str) and isinstance(record.target, str)
    return texts and isinstance(record.seed, dict) and all(type(n) is int for n in lines)


def mark(row: Row, records: Mapping[Key, Record]) -> Row:
    """The row marked ``accepted`` or ``changed`` against its record, or as it was without one."""
    if row.target is None or row.seed is None:
        return row
    record = records.get(key_of(row.target, row.seed))
    if record is None:
        return row
    change = _change(record, row)
    return replace(row, record="accepted" if change is None else "changed", change=change)


def _change(record: Record, row: Row) -> str | None:
    """What differs between the record and the row, or ``None`` when they match."""
    changes = []
    if record.status != row.status.value:
        changes.append(f"status was {record.status}, now {row.status.value}")
    if record.only_legacy != row.only_legacy:
        was, now = _lines(record.only_legacy), _lines(row.only_legacy)
        changes.append(f"only legacy was {was}, now {now}")
    if record.only_v2 != row.only_v2:
        changes.append(f"only v2 was {_lines(record.only_v2)}, now {_lines(row.only_v2)}")
    return "; ".join(changes) or None


def _lines(lines: Sequence[int]) -> str:
    return ", ".join(map(str, lines)) or "none"


def passes(row: Row) -> bool:
    """A row with a record passes when accepted; one without, only as same or left out."""
    if row.record is not None:
        return row.record == "accepted"
    return row.status in PASSING


def rewritten(accepted: Accepted, rows: Iterable[Row]) -> list[Record]:
    """The records ``--accept`` writes, sorted by set, target and seed."""
    records = {key: record for key, record in accepted.records.items() if key in accepted.listed}
    for row in rows:
        if row.target is None or row.seed is None:
            continue
        key = key_of(row.target, row.seed)
        records.pop(key, None)
        if row.status not in PASSING:
            records[key] = _record_of(row, row.target, row.seed)
    return sorted(records.values(), key=lambda record: (record.set, *record.key))


def _record_of(row: Row, target: str, seed: Mapping[str, object]) -> Record:
    return Record(
        set=row.set,
        target=target,
        seed=seed,
        status=row.status.value,
        only_legacy=row.only_legacy,
        only_v2=row.only_v2,
    )


def write_records(path: Path, records: Collection[Record]) -> None:
    """One record per line, its keys in the order the module docstring gives."""
    lines = [
        json.dumps(
            {
                "set": record.set,
                "target": record.target,
                "seed": record.seed,
                "status": record.status,
                "only_legacy": list(record.only_legacy),
                "only_v2": list(record.only_v2),
            }
        )
        for record in records
    ]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
