"""A sweep fixture: a module that exposes a bound method of a module-level instance."""


class _Dice:
    def roll(self, sides: int) -> int:
        if sides > 6:
            return sides
        return 1


_dice = _Dice()
roll = _dice.roll
