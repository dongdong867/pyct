"""Callables whose signature Python cannot read, each under a module-level name."""

import functools

builtin_alias = int
pick = max


def _f(x: int) -> int:
    return x


def _g(x: int) -> int:
    return x


# each wraps the other, so unwrapping either never ends
_f.__wrapped__ = _g
_g.__wrapped__ = _f
looped = _f


def _h(x: int) -> int:
    return x


_h.__signature__ = "not a signature"
bad_signature = _h


def _k(x: int) -> int:
    return x


_k.__signature__ = 5
wrong_signature_type = _k
partial_max = functools.partial(max, 1)
