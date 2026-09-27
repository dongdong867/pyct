"""A sweep fixture: public names that hold no function or class of this module. join and sqrt
are frozen and C code on Python 3.12; dedent is Python code in a file outside the package."""

from math import sqrt
from os.path import join
from textwrap import dedent

RATE = 2


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner


default_cart = Cart("x")


def _helper(x):
    return dedent(join(str(x), str(sqrt(RATE))))
