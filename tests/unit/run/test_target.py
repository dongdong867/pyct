import sys
from pathlib import Path

import pytest

from pyct.run.target import Target, TargetError, load_target

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


def test_load_target_imports_from_the_current_directory() -> None:
    target = load_target("targets.trace.uncalled_helper::classify")

    assert isinstance(target, Target)
    assert target.spec == "targets.trace.uncalled_helper::classify"
    assert target.file == str(REPO_ROOT / "targets" / "trace" / "uncalled_helper.py")
    assert list(target.signature.parameters) == ["x"]
    assert target.fn(x=1) == "small"


def test_load_target_names_a_module_that_does_not_import() -> None:
    with pytest.raises(TargetError, match="targets.trace.broken_import"):
        load_target("targets.trace.broken_import::anything")


def test_load_target_names_a_missing_module() -> None:
    with pytest.raises(TargetError, match="targets.trace.no_such_module"):
        load_target("targets.trace.no_such_module::f")


def test_load_target_names_a_function_the_module_lacks() -> None:
    with pytest.raises(TargetError, match="no_such_function"):
        load_target("targets.trace.uncalled_helper::no_such_function")


def test_load_target_names_a_module_with_no_python_source() -> None:
    """A compiled extension module imports and has a ``__file__``, but no source to read."""
    with pytest.raises(TargetError, match="_crypt has no Python source file"):
        load_target("_crypt::crypt")
