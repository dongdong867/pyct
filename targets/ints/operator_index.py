"""`operator.index` on a tracked int, through the module, an alias of it, or the function under
another name: followed, Python's own on anything else, and left as written where the name is
bound otherwise too."""

import operator
import operator as op
from operator import index as _index


def kept(n: int):
    k = operator.index(n)
    if k > 10:
        return 1
    return 0


def checked(year: int):
    year = _index(year)
    if not 1 <= year <= 9999:
        raise ValueError("year must be in 1..9999")
    return year


def through_an_alias(n: int):
    if op.index(n) == 7:
        return 1
    return 0


def of_a_bool(n: int):
    if operator.index(n > 3) == 1:
        return 1
    return 0


def of_a_str(s: str):
    return operator.index(s)


def with_a_keyword(n: int):
    return operator.index(a=n)


def plain():
    return operator.index(True) + _index(5)
