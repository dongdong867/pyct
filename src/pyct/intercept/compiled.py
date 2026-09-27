"""The code Python would run for a module, with its compares substituted."""

from __future__ import annotations

import ast
import types
from typing import cast

from pyct.core.values import own
from pyct.intercept.substitute import substitute


class SubstitutionError(Exception):
    """pyct could not substitute a module that compiles as written. A pyct bug."""


def substituted_code(source: bytes, path: str) -> types.CodeType:
    """Parse the source, substitute its compares, and compile it against the file's own path.

    ``path`` becomes every code object's file name, so a line tracer, a
    fork and a traceback name the file as written. The source's encoding
    declaration counts, as in Python's own import. A module that does not
    compile raises Python's own SyntaxError, marked as the target's, since
    pyct parses and compiles it for the target. A failure pyct causes is a
    `SubstitutionError`: the transform raised, or its tree does not compile
    where the source does.
    """
    tree = cast(ast.Module, own(ast.parse, source, filename=path))
    try:
        substituted = substitute(tree)
    except Exception as error:
        raise SubstitutionError(f"cannot substitute {path}: {error!r}") from error
    try:
        return compile(substituted, path, "exec", dont_inherit=True)
    except Exception as error:
        # the compiler's own checks run past the parser: a module the parser takes may still not
        # compile, and that raise is the module's. Only one that compiles as written is pyct's
        own(compile, source, path, "exec", dont_inherit=True)
        raise SubstitutionError(f"cannot substitute {path}: {error!r}") from error
