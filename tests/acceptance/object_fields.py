"""The targets, seeds and folders the a-rewrite-reads-an-object-s-fields story's acceptance tests
share: the fixtures in ``targets/rewrites/objects.py`` and ``targets/rewrites/hooks.py``, the
folder each hook writes its file in, and the log a noisy constructor appends to."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.results.record import Source
from tests.acceptance.llm_rewrites import Rewritten, file_of, llm_said

OBJECTS = "targets.rewrites.objects"
HOOKS = "targets.rewrites.hooks"
# `pay(order)`: `if float(order.code) == 1e-30:` on line 5, `return 1` on line 6
PAY = f"{OBJECTS}::pay"
PAY_AT = f"llm: rewrite for {file_of('objects')}:5:7"
# `pay_hinted(order: Order)`, the same lines on 11 and 12
PAY_HINTED = f"{OBJECTS}::pay_hinted"
HINTED_AT = f"llm: rewrite for {file_of('objects')}:11:7"
# `charge(order, s)`: `if float(s) == 1e-30:` on line 9, `return 1` on line 10
CHARGE = f"{HOOKS}::charge"
CHARGE_AT = f"llm: rewrite for {file_of('hooks')}:9:7"
READS_CODE = 'order.code == "1e-30"'
TOOK = "took the wanted side"


def form(cls: str, module: str = OBJECTS, **fields: object) -> dict[str, object]:
    """The seed's object form of ``module``'s class ``cls``, from ``fields``."""
    return {"__class__": f"{module}::{cls}", **fields}


def order_seed(cls: str = "Order") -> dict[str, object]:
    """The seed of ``pay``, its object of the class ``cls``."""
    return {"order": form(cls, code="0")}


def charge_seed(cls: str, **fields: object) -> dict[str, object]:
    """The seed of ``charge``, its object of ``hooks``' class ``cls``."""
    return {"order": form(cls, HOOKS, **({"code": "0"} | fields)), "s": "0"}


def tries(ran: Rewritten, at: str) -> list[str]:
    """Each try line at ``at``, its prefix cut off."""
    prefix = f"{at}, "
    return [line[len(prefix) :] for line in llm_said(ran.said) if line.startswith(prefix)]


def covers(ran: Rewritten, line: int, *, rewrite: bool = True) -> list[dict[str, object]]:
    """The arguments of each input that covers ``line``, from a rewrite's ask when ``rewrite``."""
    return [
        dict(record.args)
        for record in ran.records
        if line in record.covered_lines and (not rewrite or record.source is Source.REWRITE)
    ]


def instance(module: str, cls: str, *args: object) -> object:
    """An instance of the loaded target module's class, made once the target has loaded."""
    return getattr(sys.modules[module], cls)(*args)


@pytest.fixture(name="hooks")
def hooks_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """The folder each hook writes its file in; the test fails when any file is there after
    it."""
    folder = tmp_path / "hooks"
    folder.mkdir()
    monkeypatch.setenv("PYCT_TEST_HOOKS", str(folder))
    yield folder
    assert sorted(os.listdir(folder)) == []


@pytest.fixture(name="noisy")
def noisy_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The log ``Noisy``'s constructor appends its process id to, one line a build."""
    log = tmp_path / "noisy.log"
    monkeypatch.setenv("PYCT_TEST_NOISY_LOG", str(log))
    return log


def builds_by(log: Path) -> tuple[int, int]:
    """How many builds the log holds from this process and from any other."""
    pids = log.read_text().split() if log.exists() else []
    here = sum(pid == str(os.getpid()) for pid in pids)
    return here, len(pids) - here
