"""Where a run's path left the plan it was solved for."""

from pyct.core.branch import Branch


def compare(planned: tuple[Branch, ...], actual: tuple[Branch, ...]) -> int | None:
    """The first position where ``actual`` stops following ``planned``.

    A fork is followed when it happens at the same site and takes the same
    side. A run that goes on forking past the plan still followed it, so
    only the planned positions are read.
    """
    for position, wanted in enumerate(planned):
        if position >= len(actual) or not _follows(wanted, actual[position]):
            return position
    return None


def _follows(wanted: Branch, took: Branch) -> bool:
    """Whether one fork of a run is the fork the plan asked for at that position."""
    return took.site == wanted.site and took.taken == wanted.taken
