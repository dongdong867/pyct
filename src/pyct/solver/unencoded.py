"""The error a path no program can write raises."""


class UnencodedError(ValueError):
    """A path no program can write: a miss, not a broken rule of pyct's own."""
