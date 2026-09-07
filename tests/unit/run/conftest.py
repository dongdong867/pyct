import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _forget_fixture_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the loader in the state a fresh interpreter is in: no repo root on the path.

    pytest's prepend import mode has already put the repo root on ``sys.path``
    because ``tests/`` is a package, so it has to be taken off again. Otherwise
    the loader's ``if cwd not in sys.path`` guard short-circuits and the
    current-directory test proves nothing. The cached ``targets`` package goes
    too, root included: a submodule imports off the parent's ``__path__`` and
    would never consult ``sys.path`` at all.
    """
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p).resolve() != REPO_ROOT])
    for name in [n for n in sys.modules if n.split(".", 1)[0] == "targets"]:
        monkeypatch.delitem(sys.modules, name)
