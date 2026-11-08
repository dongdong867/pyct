"""The checks on one JSON object of a seed that a class is built from, at any place in the seed."""

from __future__ import annotations

import inspect
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from pyct.binding.annotations import Check, as_typed, contradictions
from pyct.binding.call import call_arguments, positional_only
from pyct.binding.resolve import checked_annotations

# the key the items passed first by position sit under, listed in a fit line when there are any
_ARGS = "__args__"


@dataclass(frozen=True)
class ObjectCheck:
    """A class, its constructor's signature as the caller read it or None, and what the
    constructor's annotations ask of the values under their keys (``checked_annotations``)."""

    built: type
    signature: inspect.Signature | None
    checks: Mapping[str, Check]

    @classmethod
    def of(cls, owner: type, signature: inspect.Signature | None) -> ObjectCheck:
        """The check for ``owner`` built through ``signature``, which the caller read.

        A ``*args`` parameter's annotation checks no key: a key of that name
        reaches the constructor through ``**kwargs``, or does not fit.
        """
        if signature is None:
            return cls(owner, None, {})
        starred = _star_args(signature)
        checks = checked_annotations(signature, owner)
        return cls(
            owner, signature, {key: each for key, each in checks.items() if key not in starred}
        )

    def lines(
        self,
        place: str,
        value: object,
        allowed: Collection[str] = frozenset(),
        positional: Sequence[object] = (),
    ) -> list[str]:
        """Every refusal line for the object at ``place``: its shape, its reserved keys, its fit,
        then its values' types.

        A value that is not a JSON object gives that one line. A key that
        starts and ends with ``__`` is refused unless it is ``allowed``, and is
        never bound. The other keys bind as the build passes them, after the
        ``positional`` items. With no signature, the fit and the types are not
        checked.
        """
        if not isinstance(value, dict):
            return [
                f"{place} must be a JSON object of {self._name}'s constructor arguments, got"
                f" {as_typed(value)}"
            ]
        lines = [
            _reserved_line(place, key) for key in value if _reserved(key) and key not in allowed
        ]
        if self.signature is None:
            return lines
        fields = {key: item for key, item in value.items() if not _reserved(key)}
        reason = fit_failure(self.signature, fields, positional)
        if reason is not None:
            parameters = ", ".join(self.signature.parameters)
            given = _bound_keys(value, positional)
            lines.append(f"{place} ({given}) does not fit {self._name}({parameters}): {reason}")
        return lines + contradictions(self.checks, fields, place)

    @property
    def _name(self) -> str:
        return self.built.__qualname__


def fit_failure(
    signature: inspect.Signature, seed: Mapping[str, object], positional: Sequence[object] = ()
) -> str | None:
    """Why the seed's keys do not bind to ``signature``, as Python's own binding says, or None
    when they bind.

    The ``positional`` items go first by position and fill the first
    parameters. Then each positional-only parameter after those that the seed
    names goes by position, as the call passes it, and the other keys by name.
    """
    values, keywords = call_arguments(positional_only(signature)[len(positional) :], seed)
    try:
        signature.bind(*positional, *values, **keywords)
    except TypeError as error:
        return str(error)
    return None


def _star_args(signature: inspect.Signature) -> set[str]:
    """The ``*args`` parameter's name, or no name for a signature without one."""
    var = inspect.Parameter.VAR_POSITIONAL
    return {name for name, parameter in signature.parameters.items() if parameter.kind is var}


def _bound_keys(value: Mapping[str, object], positional: Sequence[object]) -> str:
    """The keys the fit binds, in the seed's order, and ``__args__`` when items are passed by
    position; ``nothing`` for none."""
    bound = [key for key in value if not _reserved(key) or (key == _ARGS and positional)]
    return ", ".join(bound) or "nothing"


def _reserved(key: str) -> bool:
    return key.startswith("__") and key.endswith("__")


def _reserved_line(place: str, key: str) -> str:
    return f"{place} cannot hold {key!r}: pyct reserves keys that start and end with __"
