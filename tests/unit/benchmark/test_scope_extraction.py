"""Extract per-function scopes from source for baseline generation.

The generator walks each measured source file and emits one
:class:`FunctionScope` per *entered* function (≥1 line in the function
body was hit). Module-level code is excluded — it runs at import time
and is covered uniformly across runners, so it would dilute the metric.
Methods inside classes are emitted as independent scopes.
"""

from __future__ import annotations

from tools.benchmark.baseline import function_scopes_in_source

_TWO_FUNCTIONS = """\
def foo(x):
    if x > 0:
        return 1
    return 0


def bar(y):
    return y * 2
"""
# Line numbers:
#   1: def foo(x):
#   2:     if x > 0:
#   3:         return 1
#   4:     return 0
#   5: (blank)
#   6: (blank)
#   7: def bar(y):
#   8:     return y * 2


_CLASS_WITH_METHODS = """\
class Greeter:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"hi {self.name}"
"""
# Line numbers:
#   1: class Greeter:
#   2:     def __init__(self, name):
#   3:         self.name = name
#   4: (blank)
#   5:     def greet(self):
#   6:         return f"hi {self.name}"


def test_emits_scope_for_each_entered_function():
    executable = {1, 2, 3, 4, 7, 8}
    hit = {3, 8}  # body lines of both functions

    scopes = function_scopes_in_source(_TWO_FUNCTIONS, executable, hit, "m.py")

    scopes_by_start = {s.start_line: s for s in scopes}
    assert set(scopes_by_start) == {1, 7}
    assert scopes_by_start[1].lines == (1, 2, 3, 4)
    assert scopes_by_start[7].lines == (7, 8)
    assert all(s.file == "m.py" for s in scopes)


def test_skips_unentered_function():
    # Only foo's body lines are hit — bar stays out of the baseline.
    executable = {1, 2, 3, 4, 7, 8}
    hit = {2, 3}

    scopes = function_scopes_in_source(_TWO_FUNCTIONS, executable, hit, "m.py")

    assert len(scopes) == 1
    assert scopes[0].start_line == 1


def test_emits_scope_for_each_entered_method_in_class():
    # Only __init__ was called; greet was not.
    executable = {2, 3, 5, 6}  # method body lines (class line 1 excluded)
    hit = {3}

    scopes = function_scopes_in_source(_CLASS_WITH_METHODS, executable, hit, "m.py")

    assert len(scopes) == 1
    assert scopes[0].start_line == 2
    assert scopes[0].lines == (2, 3)


def test_module_level_hits_do_not_emit_a_scope():
    # A module with a top-level statement and a never-called function.
    src = "X = 1\n\ndef f():\n    return 2\n"
    # Lines: 1=X=1, 3=def f, 4=return 2
    executable = {1, 3, 4}
    hit = {1}  # only the module-level line ran

    scopes = function_scopes_in_source(src, executable, hit, "m.py")

    assert scopes == []


def test_returns_empty_for_empty_source():
    assert function_scopes_in_source("", set(), set(), "m.py") == []


def test_returns_empty_for_syntactically_broken_source():
    # Must fail gracefully — don't crash the generator on a bad file.
    broken = "def oops(:\n    return\n"

    assert function_scopes_in_source(broken, {1}, {1}, "m.py") == []


def test_scope_lines_include_def_header_and_all_executable_body():
    # Even if only one body line is hit, the scope must list EVERY
    # executable line in the function — not just the hit ones. The
    # baseline is the denominator; hits are applied separately.
    executable = {1, 2, 3, 4}
    hit = {3}

    scopes = function_scopes_in_source(_TWO_FUNCTIONS, executable, hit, "m.py")

    assert len(scopes) == 1
    assert scopes[0].lines == (1, 2, 3, 4)
