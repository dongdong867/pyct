"""What a concolic value does at runtime. Branch.

Each number module, and strs for a number's text, enters its tracked class in
`numbers` when it is imported, and an operation picks its answer's class
there. Importing them here fills that table before any value is built,
whichever core module a caller imports.
"""

from pyct.core import bools, floats, ints, strs

__all__ = ["bools", "floats", "ints", "strs"]
