"""Every substituted operation behaves as written on operands pyct does not track.

intercept-builtin-functions-behaves-as-written-on-plain-operands. Each program applies one
substituted shape to its operands, and runs twice in fresh namespaces: compiled as written,
and compiled as pyct substitutes it, which binds the names it calls itself.
Each pair must give the same answer, of the same type, or raise the same exception type with
the same message, and log the same calls in the same order.

The operands are a plain value of each built-in type, an object whose every method pyct may
reach logs its call, and an object whose every such method raises. Each operand is written as
a call that logs its evaluation, so the order the operands run in is in the log too.
`PROGRAMS` is the table the next substitutions add their rows to.
"""

import ast
import itertools
import types
from collections.abc import Iterator

import pytest

from pyct.intercept.substitute import substitute

# one program per shape pyct substitutes; `a` and `b` are the operands, `note` logs each one's
# evaluation, and the answer is left in `answer`
PROGRAMS: dict[str, str] = {
    "is True": "answer = note('a', a) is True",
    "is False": "answer = note('a', a) is False",
    "is not True": "answer = note('a', a) is not True",
    "True is": "answer = True is note('a', a)",
    "is bool name": "held = note('a', a) == 1\nanswer = held is note('b', b)",
    "is not bool name": "held = not note('a', a)\nanswer = note('b', b) is not held",
    "chain is bool name": "held = note('a', a) == 1\nanswer = note('c', 0) != held is note('b', b)",
    "chain in then is None": (
        "answer = note('a', a) in note('b', b) is None < note('c', 1) in [1]"
    ),
    "chain True is then is not None": "answer = True is note('a', a) is not None",
    "chain is True then is not None": "answer = note('a', a) is True is not None",
    "False is not": "answer = False is not note('a', a)",
    "not is": "answer = not (note('a', a) is True)",
    "not not is": "answer = not not (note('a', a) is False)",
    "in": "answer = note('a', a) in note('b', b)",
    "not in": "answer = note('a', a) not in note('b', b)",
    "not (in)": "answer = not (note('a', a) in note('b', b))",
    "not (not in)": "answer = not (note('a', a) not in note('b', b))",
    "if in": "if note('a', a) in note('b', b):\n    answer = 'yes'\nelse:\n    answer = 'no'",
    "while not in": "answer = 0\nwhile note('a', a) not in note('b', b):\n    answer = 1; break",
    "in literal set": "answer = note('a', a) in {1, 5, 'x', None, (1, 2)}",
    "not in literal set": "answer = note('a', a) not in {1,\n    5, 'x'}",
    "in set display": "answer = note('a', a) in {note('e', 1), 'x'}",
    "in literal dict": "answer = note('a', a) in {'x': note('v', 1), 2: 3}",
    "in dict unpacked": "answer = note('a', a) in {**note('d', {'x': 1}), 2: 3}",
    "in literal list": "answer = note('a', a) in [1,\n    'x', 3]",
    "in list display": "answer = note('a', a) in [1, note('e', 'x')]",
    "in starred list": "answer = note('a', a) in [*note('s', [1]), 'x']",
    "in literal tuple": "answer = note('a', a) in (1, 'x')",
    "in empty dict": "answer = note('a', a) in {}",
    "in repeated set": "answer = note('a', a) in {1, True, 1.0, 'x', 'x'}",
    # a chained compare: its `in` link searches through pyct, and its `is` link against True
    # or False is answered by pyct, each operand evaluated once and the chain stopping as written
    "chain in first": "answer = note('a', a) in note('b', b) != note('c', 2)",
    "chain in last": "answer = note('c', 0) != note('a', a) in note('b', b)",
    "chain not in": "answer = note('c', 0) != note('a', a) not in note('b', b)",
    "chain in literal set": "answer = note('c', 0) != note('a', a) in {1, 5, 'x'}",
    "chain in literal list": "answer = note('c', 0) != note('a', a) in [1,\n    'x']",
    "chain is True": "answer = note('b', b) != note('a', a) is True",
    "chain is not False": "answer = note('a', a) is not False == note('b', b)",
    "chain True is": "answer = True is note('a', a) != note('b', b)",
    "chain False is not": "answer = note('c', 0) == False is not note('a', a)",
    "chain in then is": "answer = note('c', 1) in note('a', a) is note('b', b)",
    "chain in then in": "answer = note('c', 1) in note('a', a) in note('b', b)",
    "chain in then <": "answer = note('c', 1) in note('a', a) < note('b', b)",
    "if chain in": (
        "if note('c', 0) != note('a', a) in note('b', b):\n    answer = 'yes'\n"
        "else:\n    answer = 'no'"
    ),
    "chain in class body": (
        "class Held(metaclass=Logging):\n    held = 0 != note('a', a) in note('b', b)\n"
        "answer = Held.held"
    ),
    # a class body whose namespace logs every name it is asked for and does not hold
    "in class body": (
        "class Held(metaclass=Logging):\n    held = note('a', a) in note('b', b)\n"
        "answer = Held.held"
    ),
    # the conversions, bare, after a dot, under `map`, and a name the module binds itself
    "int": "answer = int(note('a', a))",
    "int with a base": "answer = int(note('a', a), note('b', b))",
    "int with a keyword": "answer = int(note('a', a), base=note('b', b))",
    "float": "answer = float(note('a', a))",
    "bool": "answer = bool(note('a', a))",
    "builtins.int": "import builtins\nanswer = builtins.int(note('a', a))",
    "map int": "answer = list(map(int, note('a', a)))",
    "map float over two": "answer = list(map(float, note('a', a), note('b', b)))",
    "map bool lazily": "found = map(bool, note('a', a))\nanswer = next(found, 'none')",
    "own int": "def int(value):\n    return ('own', value)\nanswer = int(note('a', a))",
    "int in class body": (
        "class Held(metaclass=Logging):\n    held = int(note('a', a))\nanswer = Held.held"
    ),
    # a function of math, through each name an import of it binds
    "math.sqrt": "import math\nanswer = math.sqrt(note('a', a))",
    "m.copysign": "import math as m\nanswer = m.copysign(note('a', a), note('b', b))",
    "math.isclose by keyword": (
        "import math\nanswer = math.isclose(a=note('a', a), b=note('b', b), abs_tol=0.5)"
    ),
    "from math import isnan": "from math import isnan\nanswer = isnan(note('a', a))",
    "from math import fabs as size": "from math import fabs as size\nanswer = size(note('a', a))",
    "from math import *": "from math import *\nanswer = gcd(note('a', a), note('b', b))",
    "math.exp in class body": (
        "import math\nclass Held(metaclass=Logging):\n    held = math.exp(note('a', a))\n"
        "answer = Held.held"
    ),
    # a str literal's method, given each operand
    "literal find": "answer = 'xyz'.find(note('b', b))",
    "literal index": "answer = 'xyz'.index(note('b', b))",
    "literal startswith": "answer = 'xyz'.startswith(note('b', b))",
    "literal count with a start": "answer = 'xyz'.count(note('b', b), 1)",
    "literal count by keyword": "answer = 'xyz'.count(sub=note('b', b))",
    "literal split by keyword": "answer = 'x,y'.split(sep=note('b', b))",
    "literal join": "answer = ','.join(note('b', b))",
    "literal format": "answer = '{}'.format(note('b', b))",
    "if literal startswith": (
        "if 'xyz'.startswith(note('b', b)):\n    answer = 'yes'\nelse:\n    answer = 'no'"
    ),
    # every operator with a float or bool literal on the left
    **{
        f"{left} {op} b": f"answer = {left} {op} note('b', b)"
        for left in ("0.5", "True", "-2.5")
        for op in ("+", "-", "*", "/", "//", "%", "**", "<<", ">>", "&", "|", "^")
    },
    **{
        f"{left} {op} b": f"answer = {left} {op} note('b', b)"
        for left in ("0.5", "False")
        for op in ("<", "<=", ">", ">=", "==", "!=")
    },
    "if 0.5 < b": "if 0.5 < note('b', b):\n    answer = 'yes'\nelse:\n    answer = 'no'",
    "not True == b": "answer = not True == note('b', b)",
    # a name bound only to a literal, read as the literal
    "name bound to a float + b": "RATE = 0.5\nanswer = RATE + note('b', b)",
    "name bound to a bool == b": "FLAG = True\nanswer = FLAG == note('b', b)",
    "name bound to text find": "TEXT = 'xyz'\nanswer = TEXT.find(note('b', b))",
    # a name bound to a literal, read in a class body where the class's namespace answers it, is
    # read once there, beside one read the rule takes outside the class
    "name in a class body's default": (
        "RATE = 0.5\nclass Held(metaclass=Logging):\n"
        "    def m(self, x=RATE * note('b', b)):\n        return x\n"
        "answer = (Held().m(), RATE + note('a', a))"
    ),
    "name in a class body's lambda default": (
        "RATE = 0.5\nclass Held(metaclass=Logging):\n"
        "    held = (lambda z=RATE + note('b', b): z)()\n"
        "answer = (Held.held, RATE + note('a', a))"
    ),
    "name in a class body's comprehension": (
        "RATE = 0.5\nclass Held(metaclass=Logging):\n"
        "    held = [v for v in (RATE * note('b', b), 2)]\n"
        "answer = (Held.held, RATE + note('a', a))"
    ),
    "name in a class body's decorator": (
        "RATE = 0.5\nclass Held(metaclass=Logging):\n"
        "    @(lambda f, k=RATE == note('b', b): k)\n    def held(self):\n        pass\n"
        "answer = (Held.held, RATE + note('a', a))"
    ),
    "name in a method body of a class": (
        "RATE = 0.5\nclass Held(metaclass=Logging):\n"
        "    def m(self):\n        return RATE * note('b', b)\nanswer = Held().m()"
    ),
    # a name bound to a literal, rebound at run time to something else
    "name rebound through globals": (
        "RATE = 0.5\nglobals()['RATE'] = note('a', a)\nanswer = RATE * note('b', b)"
    ),
    "text name rebound through globals": (
        "TEXT = 'xyz'\nglobals()['TEXT'] = note('a', a)\nanswer = TEXT.find(note('b', b))"
    ),
}


class Logged:
    """An operand whose every method a substituted operation may reach logs its call."""

    def __init__(self, log: list[object]) -> None:
        self.log = log

    def __eq__(self, other: object) -> bool:
        self.log.append(("__eq__", type(other).__name__))
        return False

    def __hash__(self) -> int:
        self.log.append("__hash__")
        return 1

    def __contains__(self, item: object) -> object:
        self.log.append(("__contains__", type(item).__name__))
        return Answer(self.log)

    def __iter__(self) -> Iterator[int]:
        self.log.append("__iter__")
        return iter([1])

    def __bool__(self) -> bool:
        self.log.append("__bool__")
        return True

    def __int__(self) -> int:
        self.log.append("__int__")
        return 1

    def __index__(self) -> int:
        self.log.append("__index__")
        return 1

    def __float__(self) -> float:
        self.log.append("__float__")
        return 1.0

    def __add__(self, other: object) -> object:
        self.log.append(("__add__", type(other).__name__))
        return NotImplemented

    def __radd__(self, other: object) -> object:
        self.log.append(("__radd__", type(other).__name__))
        return "added"

    def __lt__(self, other: object) -> object:
        self.log.append(("__lt__", type(other).__name__))
        return NotImplemented

    def __gt__(self, other: object) -> object:
        self.log.append(("__gt__", type(other).__name__))
        return Answer(self.log)

    def __rand__(self, other: object) -> object:
        self.log.append(("__rand__", type(other).__name__))
        return "anded"

    def find(self, *args: object, **kwargs: object) -> object:
        self.log.append(("find", len(args), sorted(kwargs)))
        return -1

    def __format__(self, spec: str) -> str:
        self.log.append(("__format__", spec))
        return "logged"


class Asked(dict[str, object]):
    """A class namespace that logs each name it is asked for and does not hold."""

    log: list[object] = []

    def __missing__(self, name: str) -> object:
        Asked.log.append(("asked", name))
        raise KeyError(name)


class Logging(type):
    """A metaclass whose class bodies run in an `Asked` namespace."""

    @classmethod
    def __prepare__(metacls, name: str, bases: tuple[type, ...], **kwds: object) -> Asked:
        return Asked()


class Answer:
    """What a logged `__contains__` answers: a value Python tests for truth, logging the test."""

    def __init__(self, log: list[object]) -> None:
        self.log = log

    def __bool__(self) -> bool:
        self.log.append("answer.__bool__")
        return False


class Raising:
    """An operand whose every method a substituted operation may reach raises, naming itself."""

    def __eq__(self, other: object) -> bool:
        raise ValueError("__eq__ raised")

    def __hash__(self) -> int:
        raise ValueError("__hash__ raised")

    def __contains__(self, item: object) -> bool:
        raise ValueError("__contains__ raised")

    def __iter__(self) -> Iterator[int]:
        raise ValueError("__iter__ raised")

    def __bool__(self) -> bool:
        raise ValueError("__bool__ raised")

    def __int__(self) -> int:
        raise ValueError("__int__ raised")

    def __float__(self) -> float:
        raise ValueError("__float__ raised")

    def __add__(self, other: object) -> object:
        raise ValueError("__add__ raised")

    def __radd__(self, other: object) -> object:
        raise ValueError("__radd__ raised")

    def __gt__(self, other: object) -> object:
        raise ValueError("__gt__ raised")

    def find(self, *args: object) -> object:
        raise ValueError("find raised")

    def __format__(self, spec: str) -> str:
        raise ValueError("__format__ raised")


# the plain operands: a value of each built-in type, a container of each kind, and a value that
# is no container
PLAIN: list[object] = [
    1,
    0,
    True,
    False,
    1.0,
    "x",
    "",
    b"x",
    None,
    [1, "x"],
    (1, "x"),
    {1, "x"},
    frozenset({1}),
    {"x": 1, 1: 2},
    "xyz",
]


def operands(log: list[object]) -> list[object]:
    """Every operand, the plain ones and the two that log or raise, each built on this log."""
    return [*PLAIN, Logged(log), Raising()]


def outcome(code: types.CodeType, a_index: int, b_index: int) -> tuple[object, ...]:
    """Run the code once on the two operands, and say what it answered or raised, and logged."""
    log: list[object] = []
    Asked.log = log
    a, b = operands(log)[a_index], operands(log)[b_index]

    def note(name: str, value: object) -> object:
        log.append(("evaluated", name))
        return value

    namespace: dict[str, object] = {"a": a, "b": b, "note": note, "Logging": Logging}
    try:
        exec(code, namespace)  # noqa: S102 - the program under test is this module's own table
    except Exception as error:
        return ("raised", type(error), str(error), log)
    answer = namespace["answer"]
    return ("answered", type(answer), _comparable(answer), log)


def _comparable(answer: object) -> object:
    """The answer, with each of this module's own objects, which each run builds anew, as its
    class's name, so two runs' answers compare without asking the objects themselves."""
    if isinstance(answer, tuple):
        return tuple(_comparable(each) for each in answer)
    if isinstance(answer, Logged | Raising | Answer):
        return type(answer).__name__
    return answer


@pytest.mark.parametrize("shape", PROGRAMS)
def test_each_substituted_operation_behaves_as_written(shape: str) -> None:
    source = PROGRAMS[shape]
    written = compile(source, "<program>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<program>", "exec")
    assert ast.dump(substitute(ast.parse(source))) != ast.dump(ast.parse(source)), shape

    count = len(operands([]))
    for a_index, b_index in itertools.product(range(count), repeat=2):
        expected = outcome(written, a_index, b_index)
        assert outcome(substituted, a_index, b_index) == expected, (
            shape,
            operands([])[a_index],
            operands([])[b_index],
        )
