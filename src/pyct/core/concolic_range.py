"""ConcolicRange — symbolic range() substitute that registers loop branches.

The AST transformer in ``pyct.engine.ast_transformer`` rewrites
``range(...)`` calls in target source to ``ConcolicRange(...)`` so that
loop iteration goes through this class instead of Python's C-level
``range`` iterator. The critical difference is ``__iter__``: we use a
Python-level ``while current < self.stop`` loop, and the ``<``
comparison fires ``ConcolicInt.__lt__`` which registers a branch with
the engine for every iteration boundary. The C-level ``range`` iterator
bypasses the concolic ``__index__`` path entirely, so the loop count
never appears in the constraint pool.

This is a scoped-down port of upstream ``libct/concolic/range.py``. We
keep ``__init__``, ``__iter__``, and ``__len__`` (the pieces that matter
for benchmark targets using ``for _ in range(n)``). Other range methods
(``__contains__``, ``count``, ``index``, ``__getitem__``, slicing, etc.)
delegate to the underlying primitive ``range`` without symbolic
tracking — benchmark targets rarely need them and porting would double
the file size.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from pyct.utils.concolic_converter import unwrap_concolic, wrap_concolic

log = logging.getLogger("ct.con.range")


class ConcolicRange:
    """Symbolic ``range`` substitute installed by the AST transformer.

    Accepts the same argument shapes as Python's built-in ``range``:
    ``ConcolicRange(stop)``, ``ConcolicRange(start, stop)``, or
    ``ConcolicRange(start, stop, step)``. Stores the underlying range
    in ``self._super`` so pass-through methods can delegate.
    """

    def __init__(self, *args: Any) -> None:
        unwrapped = [unwrap_concolic(a) for a in args]
        self._super = range(*unwrapped)

        if len(args) == 1:
            start: Any = 0
            stop: Any = args[0]
            step: Any = 1
        elif len(args) == 2:
            start, stop = args
            step = 1
        else:
            start, stop, step = args

        engine = _find_engine(args)
        self.start = _as_concolic_int(start, engine)
        self.stop = _as_concolic_int(stop, engine)
        self.step = _as_concolic_int(step, engine)

    def __iter__(self) -> Iterator[Any]:
        """Yield concolic ints, registering a branch on each step check.

        The ``current < self.stop`` comparison (when step > 0) or
        ``current > self.stop`` (when step < 0) fires
        ``ConcolicInt.__lt__`` / ``__gt__`` which registers a branch
        with the engine. After enough iterations the solver sees the
        loop-count constraint and can synthesize inputs that drive
        different loop trip counts.
        """
        current = self.start
        step_concrete = unwrap_concolic(self.step)
        if step_concrete == 0:
            raise ValueError("range() arg 3 must not be zero")

        while True:
            if step_concrete > 0:
                if current < self.stop:
                    result = current
                    current = current + self.step
                    yield result
                else:
                    break
            else:
                if current > self.stop:
                    result = current
                    current = current + self.step
                    yield result
                else:
                    break

    def __len__(self) -> int:
        return self._super.__len__()

    def __contains__(self, item: Any) -> bool:
        return self._super.__contains__(unwrap_concolic(item))

    def __bool__(self) -> bool:
        return bool(self._super)

    def __repr__(self) -> str:
        return f"ConcolicRange({self._super!r})"


def _find_engine(args: tuple[Any, ...]) -> Any | None:
    """Search the argument tuple for a concolic value carrying an engine."""
    for arg in args:
        engine = getattr(arg, "engine", None)
        if engine is not None:
            return engine
    return None


def _as_concolic_int(value: Any, engine: Any | None) -> Any:
    """Return a ``ConcolicInt`` for ``value``, wrapping primitives as needed."""
    from pyct.core import Concolic
    from pyct.core.int import ConcolicInt

    if isinstance(value, ConcolicInt):
        return value
    if isinstance(value, Concolic):
        to_int = getattr(value, "to_int", None)
        if to_int is not None:
            return to_int()
    return wrap_concolic(int(unwrap_concolic(value)), None, engine)
