"""Target code that reads its caller finds the target's own line under substitution.

A warning with a stack level and ``sys._getframe`` read the frame that called the code; a
substituted call of the target's own function, and an operator a float literal's left side
runs, leave no frame of pyct's there.
"""

import warnings
from pathlib import Path

from pyct.intercept.compiled import substituted_code

MODULE = """
import sys
import warnings


def int(value):
    return sys._getframe(1).f_code.co_filename, sys._getframe(1).f_lineno


class Chained:
    def __radd__(self, other):
        warnings.warn("added", UserWarning, stacklevel=2)
        return sys._getframe(1).f_code.co_filename, sys._getframe(1).f_lineno

    def split(self, sep):
        warnings.warn("split", UserWarning, stacklevel=2)
        return sys._getframe(1).f_lineno


def converted():
    return int(1)


def added():
    return 0.5 + Chained()


def split():
    return Chained().split(",")
"""


def loaded(tmp_path: Path) -> tuple[dict[str, object], str]:
    path = tmp_path / "callers.py"
    path.write_text(MODULE)
    namespace: dict[str, object] = {"__name__": "callers"}
    exec(substituted_code(MODULE.encode(), str(path)), namespace)  # noqa: S102 - the module above
    return namespace, str(path)


def line_of(text: str) -> int:
    lines = [str(line) for line in MODULE.splitlines()]
    return lines.index(text) + 1


def test_the_target_s_own_function_called_where_a_conversion_is_written_sees_its_caller(
    tmp_path: Path,
) -> None:
    namespace, path = loaded(tmp_path)

    assert namespace["converted"]() == (path, line_of("    return int(1)"))  # pyrefly: ignore


def test_a_reflected_operator_beside_a_float_literal_sees_its_caller(tmp_path: Path) -> None:
    namespace, path = loaded(tmp_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        answer = namespace["added"]()  # pyrefly: ignore[not-callable]

    line = line_of("    return 0.5 + Chained()")
    assert answer == (path, line)
    assert [(warning.filename, warning.lineno) for warning in caught] == [(path, line)]


def test_a_method_named_as_str_s_on_the_target_s_object_sees_its_caller(tmp_path: Path) -> None:
    namespace, path = loaded(tmp_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        answer = namespace["split"]()  # pyrefly: ignore[not-callable]

    line = line_of('    return Chained().split(",")')
    assert answer == line
    assert [(warning.filename, warning.lineno) for warning in caught] == [(path, line)]
