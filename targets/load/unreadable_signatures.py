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


class _Odd:
    """A callable object whose every missing attribute raises KeyError, not AttributeError."""

    def __getattr__(self, name: str) -> object:
        raise KeyError(name)

    def __call__(self, x: int) -> int:
        return x


odd_callable = _Odd()


class _Raises:
    """A callable whose signature, when read, raises the error it was made with."""

    def __init__(self, error: BaseException) -> None:
        self.error = error

    @property
    def __signature__(self) -> object:
        raise self.error

    def __call__(self, x: int) -> int:
        return x


no_message = _Raises(RuntimeError())
two_line_message = _Raises(ValueError("first line\nsecond line"))
blank_first_line = _Raises(ValueError("\nafter a blank line"))
exits_while_read = _Raises(SystemExit(0))
