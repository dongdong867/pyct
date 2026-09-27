"""Which name reads hold a bool wherever the code binds them."""

import ast

import pytest

from pyct.intercept.bool_names import bool_names


def bools_read(source: str) -> set[str]:
    """The names read as a bool in the source, by name."""
    tree = ast.parse(source)
    found = bool_names(tree)
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and id(node) in found}


@pytest.mark.parametrize(
    ("source", "names"),
    [
        ("def f(flag: bool, n: int):\n    flag, n", {"flag"}),
        (
            "def f(*args: bool, flag: 'bool', **rest: bool):\n    args, flag, rest",
            {"flag"},
        ),
        ("done: bool = 1 < 2\ndef f():\n    done", {"done"}),
        ("x: bool\nx", set()),
        ("done, other = True, False\ndone, other", set()),
        ("class A:\n    done = True\n    def m(self):\n        done", set()),
        (
            "def f(y):\n    (done := y > 0)\n    return [done for _ in y if (seen := not y)], seen",
            {"done", "seen"},
        ),
        ("def f():\n    done = bool(1, 2) if 0 else bool(1)\n    done", set()),
        ("def f():\n    done = bool(x=1)\n    done", set()),
        ("def f():\n    done = -1\n    done", set()),
        ("def f():\n    done = g()\n    done", set()),
        ("import done\ndone", set()),
        ("from os import path as done\ndone", set()),
        ("try:\n    pass\nexcept E as done:\n    done", set()),
        ("with cm() as done:\n    done", set()),
        ("with cm():\n    pass", set()),
        ("match v:\n    case [*done] | {**done} | done:\n        done", set()),
        ("done = True\n[done for done in xs]", set()),
        ("done = True\n[x for x in done for y in x if done]", {"done"}),
        ("done = True\nlambda done: done", set()),
        ("done = True\nlambda: done", {"done"}),
        ("done = True\n@done\nclass A(done, metaclass=done):\n    done", {"done"}),
        (
            "def outer():\n    done = True\n    def inner():\n        nonlocal done\n        done",
            set(),
        ),
        ("done = 1\ndef f():\n    global done\n    done = True\n    done", set()),
        ("def f():\n    global done\n    done = True\n\ndef g():\n    done", {"done"}),
        ("def f():\n    global done\n    def g():\n        global other\n\n    done", set()),
        ("def f():\n    done = True\n    class A:\n        done", {"done"}),
    ],
)
def test_a_name_is_a_bool_where_every_binding_of_it_is_one(source: str, names: set[str]) -> None:
    assert bools_read(source) == names
