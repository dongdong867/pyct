"""A sweep fixture: a module that exposes a bound method of a class another module defines."""

from ._impl import Parser as _Parser

_p = _Parser()
parse = _p.parse
