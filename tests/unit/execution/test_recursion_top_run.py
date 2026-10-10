"""Which RecursionError is pyct's: the run of pyct's frames at the top of the stack, where it was
raised. Frames from outside the target's own code, the standard library's, do not end the run;
a frame of the target's does. More than ``MOST_OWN_FRAMES`` of pyct's in the run is pyct's own."""

import importlib
import os
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core.branch import PYCT_DIR
from pyct.execution import blame
from pyct.execution.blame import MOST_OWN_FRAMES
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import FailureKind

# a file under the standard library's directory, as a frame of `copy`'s or `json`'s names one
_STDLIB_FILE = os.path.join(os.path.dirname(os.__file__), "pyct_test_stdlib.py")


def _compiled(source: str, file: str) -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(compile(source, file, "exec"), namespace)
    return namespace


def _named(namespace: dict[str, object], name: str) -> Callable[..., object]:
    fn = namespace[name]
    assert callable(fn)
    return fn


# pyct's own chain of `n` frames, which calls `top` at its deepest
_CHAIN = """
def chain(n, top):
    if n == 1:
        return top()
    return chain(n - 1, top)
"""


def _limit_hit() -> object:
    raise RecursionError("maximum recursion depth exceeded")


def _kind_with(frames: int, top: Callable[[], object]) -> FailureKind:
    """Whose a RecursionError is, raised by ``top`` on ``frames`` of pyct's own."""
    chain = _named(_compiled(_CHAIN, f"{PYCT_DIR}/chain.py"), "chain")

    def target(x: int) -> object:
        return chain(frames, top)

    result = execute(ExecutionContext(fn=target, file=__file__), {"x": 1})
    assert result.failure is not None
    return result.failure.kind


def test_a_run_of_pyct_s_frames_at_the_ceiling_is_the_target_s() -> None:
    raiser = _named(
        _compiled("def top():\n    raise RecursionError('x')\n", f"{PYCT_DIR}/r.py"), "top"
    )

    # the chain's frames and the raiser's own, together at the ceiling
    assert _kind_with(MOST_OWN_FRAMES - 1, raiser) is FailureKind.TARGET_RAISED


def test_a_run_of_pyct_s_frames_past_the_ceiling_is_pyct_s() -> None:
    raiser = _named(
        _compiled("def top():\n    raise RecursionError('x')\n", f"{PYCT_DIR}/r.py"), "top"
    )

    assert _kind_with(MOST_OWN_FRAMES, raiser) is FailureKind.PYCT_BUG


def test_frames_of_the_standard_library_at_the_top_are_skipped() -> None:
    stdlib = _named(_compiled("def top():\n    raise RecursionError('x')\n", _STDLIB_FILE), "top")

    assert _kind_with(MOST_OWN_FRAMES + 1, stdlib) is FailureKind.PYCT_BUG


def test_a_frame_of_the_target_s_at_the_top_ends_the_run() -> None:
    assert _kind_with(MOST_OWN_FRAMES + 1, _limit_hit) is FailureKind.TARGET_RAISED


# pyct's own runaway that goes through a standard library frame on every level, as a copy does
_COPIES = """
import copy

class Loop:
    def __copy__(self):
        return copy.copy(self)

def run_away():
    return copy.copy(Loop())
"""


def test_a_runaway_of_pyct_s_through_the_standard_library_is_a_pyct_bug() -> None:
    run_away = _named(_compiled(_COPIES, f"{PYCT_DIR}/copies.py"), "run_away")

    def target(x: int) -> object:
        return run_away()

    result = execute(ExecutionContext(fn=target, file=__file__), {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG, result.failure


class _Again:
    """A target's own recursion through `copy`, with a fork of pyct's on every level."""

    def __init__(self, x: int) -> None:
        self.x = x

    def __copy__(self) -> object:
        import copy

        if self.x < 10:
            return copy.copy(self)
        return self  # pragma: no cover - the recursion never ends


def test_a_target_s_recursion_through_the_standard_library_stays_the_target_s() -> None:
    import copy

    def target(x: int) -> object:
        return copy.copy(_Again(x))

    result = execute(ExecutionContext(fn=target, file=__file__), {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED, result.failure.traceback


# a target's own recursion through a frame of pyct's on every level, from a package installed
# where libraries are; the test sets THROUGH to that frame's function
_INSTALLED_DEEP = """
THROUGH = None

def deep(n):
    if n <= 0:
        return 0
    return 1 + THROUGH(deep, n - 1)
"""


def _installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, *, namespace: bool
) -> Callable[..., object]:
    """``deep`` from a scratch package ``name`` under a folder blame reads as installed code."""
    root = tmp_path / "site-packages"
    package = root / name
    package.mkdir(parents=True)
    if not namespace:
        (package / "__init__.py").write_text("")
    (package / "walk.py").write_text(_INSTALLED_DEEP)
    monkeypatch.setattr(blame, "_OUTSIDE", (*blame._OUTSIDE, os.path.join(str(root), "")))
    monkeypatch.syspath_prepend(str(root))
    module = importlib.import_module(f"{name}.walk")
    monkeypatch.setitem(sys.modules, name, sys.modules[name])
    monkeypatch.setitem(sys.modules, f"{name}.walk", module)
    through = _compiled("def through(f, n):\n    return f(n)\n", f"{PYCT_DIR}/through.py")
    setattr(module, "THROUGH", through["through"])  # noqa: B010 - set on a module made at run time
    return _named(vars(module), "deep")


@pytest.mark.parametrize("namespace", [False, True], ids=["package", "namespace-package"])
def test_an_installed_target_s_own_recursion_stays_the_target_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, namespace: bool
) -> None:
    name = f"pyct_installed_{'ns' if namespace else 'pkg'}"
    deep = _installed(tmp_path, monkeypatch, name, namespace=namespace)

    result = execute(ExecutionContext(fn=deep, file=str(tmp_path)), {"n": 100_000})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED, result.failure.traceback


# pyct's own runaway through code a dataclass generates for a class of pyct's
_GENERATED = """
from dataclasses import dataclass

@dataclass
class Loop:
    rest: object = None

def run_away():
    first, second = Loop(), Loop()
    first.rest, second.rest = first, second
    return first == second
"""


def test_a_runaway_of_pyct_s_through_generated_code_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("pyct.generated_for_a_test")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(_GENERATED, f"{PYCT_DIR}/generated_for_a_test.py", "exec"), vars(module))
    run_away = _named(vars(module), "run_away")

    def target(x: int) -> object:
        return run_away()

    result = execute(ExecutionContext(fn=target, file=__file__), {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG, result.failure
