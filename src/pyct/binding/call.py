"""A seed, keyed by parameter name, as a call takes it."""

import inspect
from collections.abc import Mapping, Sequence


def positional_only(signature: inspect.Signature) -> tuple[inspect.Parameter, ...]:
    """The parameters a call must pass by position, in signature order.

    Read once from the signature ``load_target`` took, so each call needs no
    signature of its own.
    """
    return tuple(
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY
    )


def call_arguments(
    positional: Sequence[inspect.Parameter], args: Mapping[str, object]
) -> tuple[tuple[object, ...], dict[str, object]]:
    """The arguments by position and by name: the ``positional`` parameters by position.

    A seed names every parameter, a positional-only one too, and the call
    passes that one by position, in signature order. A position cannot be
    skipped, so a positional-only parameter the seed leaves out takes its
    default when a later one is given. One with no default ends the
    positions, and every later value stays a keyword, so Python's own binding
    says which parameter is missing.
    """
    values: list[object] = []
    given = 0
    for parameter in positional:
        if parameter.name in args:
            values.append(args[parameter.name])
            given = len(values)
        elif parameter.default is not inspect.Parameter.empty:
            values.append(parameter.default)
        else:
            break
    by_position = {parameter.name for parameter in positional[:given]}
    keywords = {name: value for name, value in args.items() if name not in by_position}
    return tuple(values[:given]), keywords
