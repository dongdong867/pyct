"""A sweep fixture: public names that hold bound methods of module-level instances, as the
standard library's random module exposes randint."""

import textwrap


class _Dice:
    def roll(self, sides: int) -> int:
        if sides > 6:
            return sides
        return 1

    @classmethod
    def make(cls, seed: int) -> "_Dice":
        return cls()


_dice = _Dice()
roll = _dice.roll
make = _Dice.make
wrap = textwrap.TextWrapper().wrap
