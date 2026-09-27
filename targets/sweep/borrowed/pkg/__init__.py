"""A sweep fixture: a class that borrows the constructor of a same-named class from outside
the package, and compiles a method of its own here."""

from ..other import Thing as _Base


class Thing(_Base):
    __init__ = _Base.__init__

    def extra(self, k: int) -> int:
        return self.n + k
