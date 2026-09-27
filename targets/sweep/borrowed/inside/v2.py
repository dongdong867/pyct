"""A sweep fixture: a class that borrows its constructor from a same-named class in another
module of the package, and compiles a method of its own here."""

from .v1 import Thing as _Base


class Thing(_Base):
    __init__ = _Base.__init__

    def extra(self, k: int) -> int:
        return self.n + k
