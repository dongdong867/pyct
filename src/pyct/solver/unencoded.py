"""The one error a program pyct cannot write raises: a miss, not a broken rule of pyct's own."""


class UnencodedError(ValueError):
    """An operation, a read or a literal on the path that no form or term writes on what it
    meets: the path is a miss, not a broken rule of pyct's own."""
