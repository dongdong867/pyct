"""A function annotated with a name that only a type checker imports.

Python 3.14 evaluates annotations when asked, so the module imports and reading the
signature raises NameError. Before 3.14 the ``def`` evaluates them, so the import fails.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


def f(x: int, y: Decimal) -> int:
    return x
