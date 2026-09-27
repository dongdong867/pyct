"""Interception: the target's package calls core where Python would not.

An import hook loads every module of the target's top-level package with a
fixed set of operations substituted where the code writes them, so a
tracked value keeps its condition through `is True` and `in`. It is
mechanical and fixed; the LLM source rewrite of the next paper is
`pyct.rewrite`, which may hand its source to the same loader.

Substituted code calls pyct through four names it binds in the module,
``__pyct_is__``, ``__pyct_is_not__``, ``__pyct_in__`` and
``__pyct_not_in__``, and each class body declares them global. The names
are reserved for pyct: a target module of the package that binds one of
them itself changes what its substituted compares call, and one that
annotates one in a class body does not load.
"""
