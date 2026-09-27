"""The text of a tracked int where code that needs text reads it, against plain Python."""

import json
import marshal
import string
import sys
import types
from collections.abc import Callable

import pytest

from pyct.core.branch import SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr


class _Holder:
    pass


def _attribute(text: str) -> object:
    holder = _Holder()
    setattr(holder, text, 1)
    return getattr(holder, text), hasattr(holder, text)


# code that reads text and takes a str subclass as it takes a str: each answers as plain Python
TAKES_A_SUBCLASS: dict[str, Callable[[str], object]] = {
    "setattr and getattr": _attribute,
    "json.dumps": json.dumps,
    "a dict key": lambda text: {text: 1}["7"],
    "str.translate": lambda text: "a".translate({97: text}),
    "str.maketrans": lambda text: str.maketrans({text: "x"}),
    "a keyword name": lambda text: vars(types.SimpleNamespace(**{text: 1})),
    "string.Template": lambda text: string.Template("$x").substitute(x=text),
    "bytes": lambda text: bytes(text, "ascii"),
    "compile": lambda text: eval(compile(text, "<text>", "eval")),
}

# code that takes an exact str alone, and refuses any subclass of it as it refuses a tracked str
EXACT_ONLY: dict[str, Callable[[str], object]] = {
    "sys.intern": sys.intern,
    "marshal.dumps": marshal.dumps,
}


def _text() -> ConcolicStr:
    sink: list[SinkItem] = []
    text = str(ConcolicInt.made(7, expression="n", sink=sink))
    assert isinstance(text, ConcolicStr)
    return text


@pytest.mark.parametrize("call", TAKES_A_SUBCLASS.values(), ids=list(TAKES_A_SUBCLASS))
def test_an_ints_text_reads_as_plain_pythons(call: Callable[[str], object]) -> None:
    assert call(_text()) == call("7")


@pytest.mark.parametrize("call", EXACT_ONLY.values(), ids=list(EXACT_ONLY))
def test_code_that_takes_an_exact_str_alone_refuses_an_ints_text(
    call: Callable[[str], object],
) -> None:
    class Text(str):
        pass

    call("7")
    with pytest.raises((TypeError, ValueError)) as plain:
        call(Text("7"))
    with pytest.raises(type(plain.value)) as raised:
        call(_text())

    # the refusal names the type it met, so only the type of the error is compared
    assert type(raised.value) is type(plain.value)
