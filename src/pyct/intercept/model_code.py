"""Code the LLM wrote, compiled under the target's substitutions, in the form a tool allows.

A tool hands in the model's text, the name its code objects carry, and its
own form check, which reads the parsed tree and returns the reason it
refuses it, or the tree to compile, rewritten as the tool needs. The tree
then takes the substitutions the target's own modules take
(`pyct.intercept.substitute`), and compiles as
`pyct.intercept.compiled.substituted_code` compiles a module. Nothing of
the code runs here, not even its ``def`` statements: model code runs only
in a child of pyct's process (`pyct.run.model_runs`). Decision
llm-model-written-code-runs-only-in-a-forked-child-or-not-at-all.
"""

from __future__ import annotations

import ast
import types
import warnings
from collections.abc import Callable
from dataclasses import dataclass

from pyct.execution.blame import one_line
from pyct.intercept.compiled import SubstitutionError
from pyct.intercept.substitute import substitute

# a tool's check of the model's code: the reason it refuses the tree, or the tree to compile
type FormCheck = Callable[[ast.Module], ast.Module | str]

# what the parser and the compiler raise on text they refuse: a long reply can be too deep for
# either, which they say as a RecursionError or a MemoryError
_REFUSALS = (SyntaxError, ValueError, RecursionError, MemoryError)


@dataclass(frozen=True)
class Refused:
    """Why model-written code did not compile: the check's reason, or the parser's or the
    compiler's own."""

    reason: str


def compile_model_code(text: str, file: str, check: FormCheck) -> types.CodeType | Refused:
    """The module code of the model's text, in the form ``check`` returns it and substituted,
    each code object named ``file``; or why it was refused.

    The checked tree is compiled as it is first, so a tree that does not
    compile is the model's; one that compiles only before its substitutions
    is pyct's `SubstitutionError`. A warning Python gives about the code,
    such as an invalid escape in a regex written without a raw string, is
    not shown, since stderr is pyct's.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return _compiled(text, file, check)


def _compiled(text: str, file: str, check: FormCheck) -> types.CodeType | Refused:
    try:
        tree = ast.parse(text, filename=file)
    except _REFUSALS as error:
        return Refused(f"does not parse: {one_line(error)}")
    checked = check(tree)
    if isinstance(checked, str):
        return Refused(checked)
    ast.fix_missing_locations(checked)
    try:
        compile(checked, file, "exec", dont_inherit=True)
    except _REFUSALS as error:
        return Refused(f"does not compile: {one_line(error)}")
    return _substituted(checked, file)


def _substituted(tree: ast.Module, file: str) -> types.CodeType:
    """The tree, which compiles as it is, substituted and compiled. A failure here is pyct's."""
    try:
        return compile(substitute(tree), file, "exec", dont_inherit=True)
    except Exception as error:
        raise SubstitutionError(f"cannot substitute {file}: {error!r}") from error
