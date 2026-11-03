"""What a concolic value does at runtime. Branch.

Each number module, and strs for a number's text, enters its tracked class in
`numbers` when it is imported, and an operation picks its answer's class
there. Importing them here fills that table before any value is built,
whichever core module a caller imports. So does `bases`, the table of each
tracked class's base type, which the classes read as they answer.
"""

# imported for their entries by full name: `from pyct.core.strs import strs` here would bind
# the module over the folder core/strs/
import pyct.core.entry.bases
import pyct.core.numbers.bools
import pyct.core.numbers.floats
import pyct.core.numbers.ints
import pyct.core.strs.strs  # noqa: F401
