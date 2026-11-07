"""An object whose attribute raises as it is read, so a path through it cannot be followed."""


class Shelf:
    @property
    def fetch(self):
        raise RuntimeError("the shelf is locked")

    @property
    def count(self):
        raise ValueError("no stock")


shelf = Shelf()
