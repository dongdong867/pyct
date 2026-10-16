"""What a run is for: covering every line and branch, or going on past that for failures."""

from enum import StrEnum


class Goal(StrEnum):
    """What a run is for, in the words ``--goal`` takes.

    ``COVERAGE`` stops the run once every line and branch is covered.
    ``BUGS`` goes on past it, so the run can still find an input that only
    raises on a line already covered, and stops as runs did before the goal.
    """

    COVERAGE = "coverage"
    BUGS = "bugs"
