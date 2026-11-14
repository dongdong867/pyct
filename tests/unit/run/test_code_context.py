"""The code a seeds ask sends: the target's, then its same-package callees, breadth first; and the
code a rewrites ask sends: the function around one line; and the code a summaries ask sends: the
function around a piece, the piece marked, then its callees."""

import inspect
import sys
from pathlib import Path

import pytest

from pyct.run.code_context import MARK_END, MARK_START, code_around, code_context, code_with_piece
from pyct.run.target import Target, load_target


def headers(code: str) -> list[str]:
    return [line for line in code.splitlines() if line.startswith("# ")]


def test_the_target_comes_first_then_a_callee_in_another_module_of_its_package() -> None:
    code = code_context(load_target("targets.llm.seeds::f"))

    assert headers(code) == ["# targets.llm.seeds.f", "# targets.llm.helpers.sign"]
    assert "def f(x: int):\n    if x == 1234:" in code
    assert "def sign(x: int) -> int:" in code


def test_callees_go_breadth_first_once_each_and_none_from_another_package() -> None:
    code = code_context(load_target("targets.llm.calls::outer"))

    # outer calls sign and middle, middle calls outer again and last; json.dumps and len are
    # not the package's, and last's calls on a local list, through a module's own __getattr__
    # and on a subscript lead to no function pyct reads without running code
    assert headers(code) == [
        "# targets.llm.calls.outer",
        "# targets.llm.helpers.sign",
        "# targets.llm.calls.middle",
        "# targets.llm.calls.last",
    ]


def test_a_method_brings_its_class_s_constructor() -> None:
    code = code_context(load_target("targets.classes.cart::Cart.total"))

    assert headers(code) == [
        "# targets.classes.cart.Cart.total",
        "# targets.classes.cart.Cart.__init__",
    ]
    # a method's code keeps its own indentation out
    assert "def total(self, discount):\n    self.last = discount" in code


def test_the_code_holds_whole_functions_up_to_the_limit() -> None:
    whole = code_context(load_target("targets.llm.calls::outer"))
    sections = whole.split("\n\n# ")

    cut = code_context(load_target("targets.llm.calls::outer"), limit=len(sections[0]) + 5)

    # the target always goes whole; a callee that does not fit is left out, never cut
    assert headers(cut) == ["# targets.llm.calls.outer"]
    assert cut == sections[0]


def test_a_method_s_calls_through_self_and_its_class_lead_to_the_class_s_functions() -> None:
    code = code_context(load_target("targets.llm.calls::Counter.bump"))

    assert headers(code) == [
        "# targets.llm.calls.Counter.bump",
        "# targets.llm.calls.Counter.__init__",
        "# targets.llm.calls.Counter.step",
        "# targets.llm.calls.Counter.twice",
    ]


def test_a_class_called_through_cls_leads_to_its_constructor() -> None:
    code = code_context(load_target("targets.classes.cart::Cart.from_text"))

    assert headers(code) == [
        "# targets.classes.cart.Cart.from_text",
        "# targets.classes.cart.Cart.__init__",
    ]


def test_a_function_python_has_no_source_for_is_left_out() -> None:
    made = eval("lambda x: x")  # noqa: S307
    target = Target("m::made", made, "m.py", inspect.signature(made))

    assert code_context(target) == ""


def helper(x: int) -> int:
    return x + 1


class Notes:
    def told(self, x: int) -> int:
        text = """
this line starts at column 0, so dedenting leaves the method indented
"""
        return helper(x) + len(text)


def here(name: str, fn: object) -> Target:
    return Target(f"{__name__}::{name}", fn, __file__, inspect.signature(fn))  # type: ignore[arg-type]


def test_a_method_holding_a_string_line_at_column_0_still_leads_to_its_callees() -> None:
    code = code_context(here("Notes.told", Notes.told))

    assert headers(code) == [f"# {__name__}.Notes.told", f"# {__name__}.helper"]
    assert "this line starts at column 0" in code


def nowhere(x: int) -> int:
    return x


nowhere.__module__ = None  # type: ignore[assignment]


def calls_nowhere(x: int) -> int:
    return nowhere(x)


def test_a_callee_that_names_no_module_is_left_out() -> None:
    code = code_context(here("calls_nowhere", calls_nowhere))

    assert headers(code) == [f"# {__name__}.calls_nowhere"]


def test_code_python_cannot_parse_alone_leads_to_no_callee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspect, "getsource", lambda _: "    x = (\n")

    code = code_context(here("calls_nowhere", calls_nowhere))

    assert code == f"# {__name__}.calls_nowhere\nx = ("


def write(tmp_path: Path, text: str) -> str:
    file = tmp_path / "m.py"
    file.write_text(text)
    return str(file)


def test_the_code_around_a_line_is_its_innermost_function_dedented(tmp_path: Path) -> None:
    file = write(
        tmp_path,
        "x = 1\n\n\nclass C:\n    @staticmethod\n    def f(s):\n"
        "        def g(n):\n            return n > 0\n        return g\n",
    )

    assert code_around(file, 8) == "def g(n):\n    return n > 0"
    assert code_around(file, 9).startswith("@staticmethod\ndef f(s):")
    assert code_around(file, 1).startswith("x = 1\n")


def test_the_code_around_a_line_in_a_long_function_is_cut_to_the_lines_around_it(
    tmp_path: Path,
) -> None:
    body = "".join(f"    n += {at}\n" for at in range(1, 400))
    file = write(tmp_path, f"def f(n):\n{body}    return n\n")

    middle = code_around(file, 201, most=10).splitlines()
    end = code_around(file, 401, most=10).splitlines()

    assert middle == [f"n += {at}" for at in range(195, 205)]
    assert end[-1] == "return n" and len(end) == 10


def test_a_file_that_does_not_read_gives_no_code(tmp_path: Path) -> None:
    assert code_around(str(tmp_path / "gone.py"), 1) == ""


LOOPED = """\
def helper(n):
    return n + 1


class Box:
    def f(self, s):
        t = 0
        for c in s:
            t = helper(t)
        return t
"""


def test_the_code_around_a_piece_marks_it_and_brings_the_function_s_callees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "piece_context"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "m.py").write_text(LOOPED)
    monkeypatch.syspath_prepend(str(tmp_path))
    target = load_target("piece_context.m::helper")

    code = code_with_piece(target, str(package / "m.py"), (8, 9))

    assert code == (
        "# piece_context.m.Box.f\n"
        "def f(self, s):\n"
        "    t = 0\n"
        f"    {MARK_START}\n"
        "    for c in s:\n"
        "        t = helper(t)\n"
        f"    {MARK_END}\n"
        "    return t\n"
        "\n"
        "# piece_context.m.helper\n"
        "def helper(n):\n"
        "    return n + 1"
    )


# globals whose class, read through ``__class__``, runs code: one raises, as a lazy object's
# setup can, and one keeps a mark in ``SEEN``
LAZY = """

SEEN = []


class Raises:
    @property
    def __class__(self):
        raise RuntimeError("set up")


class Marks:
    @property
    def __class__(self):
        SEEN.append("ran")
        return Marks


settings = Raises()
marked = Marks()
Box.settings = Raises()
Box.marked = Marks()
"""


class Unreadable:
    """An entry of ``sys.modules`` each of whose attribute reads raises, as a lazy module's load
    can."""

    def __getattribute__(self, name: str) -> object:
        raise RuntimeError(f"read {name}")


def test_reading_the_loaded_module_for_a_piece_runs_none_of_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "lazy_context"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "m.py").write_text(LOOPED + LAZY)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(sys.modules, "lazy_entry", Unreadable())
    target = load_target("lazy_context.m::helper")
    module = sys.modules["lazy_context.m"]

    code = code_with_piece(target, str(package / "m.py"), (8, 9))

    assert code.startswith(f"# lazy_context.m.Box.f\ndef f(self, s):\n    t = 0\n    {MARK_START}")
    assert code.endswith("# lazy_context.m.helper\ndef helper(n):\n    return n + 1")
    assert vars(module)["SEEN"] == []


CALLS_LAZY = """
def calls(s):
    settings(s)
    marked(s)
    Box.settings(s)
    Box.marked(s)
    return helper(s)
"""


def test_following_the_calls_to_the_target_s_objects_runs_none_of_their_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "lazy_calls"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "m.py").write_text(LOOPED + LAZY + CALLS_LAZY)
    monkeypatch.syspath_prepend(str(tmp_path))
    target = load_target("lazy_calls.m::calls")

    code = code_context(target)

    assert headers(code) == ["# lazy_calls.m.calls", "# lazy_calls.m.helper"]
    assert vars(sys.modules["lazy_calls.m"])["SEEN"] == []


def test_the_code_around_a_piece_of_a_module_not_loaded_is_its_function_marked(
    tmp_path: Path,
) -> None:
    file = write(tmp_path, "def f(s):\n    t = [c for c in s]\n    return t\n")

    code = code_with_piece(load_target("targets.llm.seeds::f"), file, (2, 2))

    assert (
        code == f"def f(s):\n    {MARK_START}\n    t = [c for c in s]\n    {MARK_END}\n    return t"
    )


def test_a_piece_in_a_file_that_does_not_read_gives_no_code(tmp_path: Path) -> None:
    target = load_target("targets.llm.seeds::f")

    assert code_with_piece(target, str(tmp_path / "gone.py"), (1, 2)) == ""
