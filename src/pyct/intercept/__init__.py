"""Interception: the target's package calls core where Python would not.

An import hook loads every module of the target's top-level package with a
fixed set of operations substituted where the code writes them, so a
tracked value keeps its condition through `is True`, `in`, a call written
`int(...)`, `float(...)` or `bool(...)`, a plain str's method given a
tracked str, and an operator a plain float or bool on the left would answer
alone. It is mechanical and fixed; the LLM source rewrite of the next paper
is `pyct.rewrite`, which may hand its source to the same loader.

Substituted code calls pyct through dunder names it binds in the module,
one per function of `pyct.core.substitutes`, such as ``__pyct_in__``,
``__pyct_call__`` and ``__pyct_add__``, importing those it calls, and each
class body declares them global. The names are reserved for pyct: a target
module of the package that binds one of them itself changes what its
substituted operations call, and one that annotates one in a class body
does not load.
"""
