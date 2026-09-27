"""What a concolic value does at runtime. Branch.

Each number module, and strs for a number's text, enters its tracked class in
`numbers` when it is imported, and an operation picks its answer's class
there. Importing them here fills that table before any value is built,
whichever core module a caller imports. So does `bases`, the table of each
tracked class's base type, which the classes read as they answer.
"""

from pyct.core import bases, bools, floats, ints, strs

__all__ = ["bases", "bools", "floats", "ints", "strs"]
