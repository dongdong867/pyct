"""A seed, keyed by parameter name, as a call takes it."""

import inspect
from collections.abc import Mapping


def call_arguments(
    signature: inspect.Signature, args: Mapping[str, object]
) -> tuple[tuple[object, ...], dict[str, object]]:
    """The arguments by position and by name: positional-only parameters by position.

    A seed names every parameter, a positional-only one too, and the call
    passes that one by position, in signature order. A position cannot be
    skipped, so a positional-only parameter the seed leaves out takes its
    default when a later one is given. One with no default ends the
    positions, and every later value stays a keyword, so Python's own binding
    says which parameter is missing.
    """
    positional: list[object] = []
    given = 0
    for name, parameter in signature.parameters.items():
        if parameter.kind is not inspect.Parameter.POSITIONAL_ONLY:
            break
        if name in args:
            positional.append(args[name])
            given = len(positional)
        elif parameter.default is not inspect.Parameter.empty:
            positional.append(parameter.default)
        else:
            break
    by_position = list(signature.parameters)[:given]
    keywords = {name: value for name, value in args.items() if name not in by_position}
    return tuple(positional[:given]), keywords
