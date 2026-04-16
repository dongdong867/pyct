"""Class fixture mirroring sympy.ntheory.ecm.Point's structure.

Has a class-level docstring and a method-level docstring, so the gap
between the class header line and the first body statement spans
multiple non-executable lines. The class header and method header are
distinct executable statements in coverage.py's analysis.
"""


class DocstringedPoint:
    """A point in 4-space.

    Mirrors the docstringed class-with-trivial-__init__ shape that
    exposed the class-target coverage bug in the library benchmark.
    """

    def __init__(self, x, y, z, m):
        """Store four coordinates as attributes."""
        self.x = x
        self.y = y
        self.z = z
        self.m = m
