"""Where a value sits in a seed, written as the access that reaches it in Python."""


def step_in(place: str, key: object) -> str:
    """The place one step further in: ``self`` and ``'owner'`` give ``self['owner']``, and
    ``rows`` and ``0`` give ``rows[0]``."""
    return f"{place}[{key!r}]"
