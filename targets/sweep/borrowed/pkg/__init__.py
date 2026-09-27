"""A sweep fixture: a class that borrows the constructor of a same-named class from outside
the package without inheriting from it, and compiles a method of its own here."""

from ..other import Thing as _Other


class Thing:
    __init__ = _Other.__init__

    def extra(self, k: int) -> int:
        return self.n + k
