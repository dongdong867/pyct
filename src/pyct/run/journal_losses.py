"""The recorded runs of an input's loss sites as their journal records hold them, written by
``journal`` and read back by ``journal_reader``.

A loss record holds a recorded run of a loss site (``LossRun``): its site's
line and column as two i64, how many values went in and whether it names a
callee as two u32, then its file, its name and its kind, for each value
going in its name, ``1`` or ``0`` for whether it was tracked, and its JSON
text, then the answer's JSON text, and, for a callee, its module, its
qualified name, its code's file and its first line, each empty when it has
none, a NUL between each.

Each field is written as UTF-8 that keeps a lone surrogate, as a file's name can hold one.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Sequence

from pyct.core.entry.losses import ANSWER
from pyct.core.foundation.branch import (
    Callee,
    Changed,
    GoingIn,
    LossKind,
    LossRun,
    Site,
)

# a recorded run's site's line and column, how many values went in and whether it names a callee
RUN_HEAD = struct.Struct("<qqII")

# how a reader makes the one ``Site`` of a place from its file, line and column
type Sites = Callable[[str, int, int], Site]


def loss_payload(run: LossRun) -> bytes:
    """A recorded run of a loss site, as its record's payload."""
    site, callee = run.site, run.callee
    fields = [site.file, run.name, run.kind.value, *_written(run.going_in)]
    fields.append(run.changed[0].value)
    if callee is not None:
        line = "" if callee.line is None else str(callee.line)
        fields += [callee.module, callee.qualname, callee.file or "", line]
    head = RUN_HEAD.pack(site.line, site.col, len(run.going_in), callee is not None)
    return head + _joined(fields)


def loss_run(payload: bytes, sites: Sites) -> LossRun:
    """A recorded run of a loss site, read from its record's payload."""
    line, col, going_in, named = RUN_HEAD.unpack_from(payload)
    file, name, kind, *fields = _fields(payload)
    if named not in (0, 1) or len(fields) != 3 * going_in + 1 + 4 * named:
        raise ValueError("a loss run holds three fields a value going in, its answer, its callee")
    ins = _going_in(fields[: 3 * going_in])
    answer, *callee = fields[3 * going_in :]
    called = _callee(callee) if named else None
    changed = (Changed(ANSWER, answer),)
    return LossRun(sites(file, line, col), name, LossKind(kind), ins, changed, called)


def _written(going_in: Sequence[GoingIn]) -> list[str]:
    fields: list[str] = []
    for held in going_in:
        fields += [held.name, "1" if held.tracked else "0", held.value]
    return fields


def _joined(fields: Sequence[str]) -> bytes:
    return "\0".join(fields).encode(errors="surrogatepass")


def _fields(payload: bytes) -> list[str]:
    return payload[RUN_HEAD.size :].decode(errors="surrogatepass").split("\0")


def _going_in(fields: Sequence[str]) -> tuple[GoingIn, ...]:
    """The values going in, three fields each: a name, ``1`` or ``0``, a value."""
    held = [fields[at : at + 3] for at in range(0, len(fields), 3)]
    if any(tracked not in ("0", "1") for _, tracked, _ in held):
        raise ValueError("a name going in is marked 1 for tracked or 0")
    return tuple(GoingIn(name, value, tracked == "1") for name, tracked, value in held)


def _callee(fields: Sequence[str]) -> Callee:
    module, qualname, file, line = fields
    return Callee(module, qualname, file or None, int(line) if line else None)
