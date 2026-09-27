"""A str literal's own method given a tracked str, run as it runs on a tracked str."""

from __future__ import annotations

import types
from typing import cast

from pyct.core.branch import Downgrade
from pyct.core.str_operands import literal
from pyct.core.strs import ConcolicStr
from pyct.core.values import own


def on_text(method: types.BuiltinMethodType, /, *args: object, **kwargs: object) -> object:
    """A plain str's own method, called with a tracked str, as it runs on a tracked str.

    ``method`` is the plain str's bound method, and one argument is a
    tracked str. The call runs as the method runs on a tracked str holding
    the plain one's text, with that text a literal in the expression:
    `"abc".find(s)` is `["find", "'abc'", "s"]`. A form pyct does not teach is
    a downgrade named by the method, as it is for a tracked receiver. A call
    with a keyword, and a text holding a character past the last one cvc5
    holds, are the method's own answer, or its own refusal in its own words,
    and a downgrade named by the method.
    """
    text = str.__str__(cast(str, method.__self__))
    name = method.__name__
    sink = next(arg.sink for arg in (*args, *kwargs.values()) if type(arg) is ConcolicStr)
    form = literal(text, ConcolicStr)
    if form is None or kwargs:
        # through str, as the written call reaches it, so a refusal reads in its words
        answer = own(getattr(str, name), text, *args, **kwargs)
        sink.append(Downgrade(name=name))
        return answer
    receiver = ConcolicStr.made(text, expression=form, sink=sink)
    return getattr(ConcolicStr, name)(receiver, *args, **kwargs)
