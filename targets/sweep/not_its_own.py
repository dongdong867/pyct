"""A sweep fixture: public names that hold no function or class of this module."""

from math import sqrt
from os.path import join

RATE = 2


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner


default_cart = Cart("x")


def _helper(x):
    return join(str(x), str(sqrt(RATE)))
