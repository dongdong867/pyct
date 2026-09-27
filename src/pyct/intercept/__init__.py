"""Interception: the target's package calls core where Python would not.

An import hook loads every module of the target's top-level package with a
fixed set of operations substituted where the code writes them, and runs
it with `len`, `ord` and `chr` bound to pyct's own in its builtins, so a
tracked value keeps its condition through `is True`, `in`, a call written
`int(...)`, `float(...)` or `bool(...)`, a str literal's method given a
tracked str, an operator with a float or bool literal on the left, each
also where the code writes a name bound only to such a literal
(`pyct.intercept.constants`), the value a `return` in a `__bool__` method
gives back, which CPython takes only as an exact bool, and the three
builtins. It is mechanical and
fixed, one to one, and not a rewrite; the LLM source rewrite of the next
paper is `pyct.rewrite`, which may hand its source to the same loader.

Substituted code calls pyct through dunder names it binds in the module,
one per function of `pyct.core.substitutes`, such as ``__pyct_in__``,
``__pyct_call__`` and ``__pyct_handed__``, importing those it calls, and each
class body declares them global. The names are reserved for pyct: a target
module of the package that binds one of them itself changes what its
substituted operations call, and one that annotates one in a class body
does not load.
"""
