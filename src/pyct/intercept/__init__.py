"""Interception: the target's package calls core where Python would not.

An import hook loads every module of the target's top-level package with a
fixed set of operations substituted where the code writes them, so a
tracked value keeps its condition through `is True` and `in`. It is
mechanical and fixed; the LLM source rewrite of the next paper is
`pyct.rewrite`, which may hand its source to the same loader.
"""
