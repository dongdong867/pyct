"""An `except ValueError:` block the solver cannot reach, since pyct does not follow `int(s, 16)`,
and that `{"s": "x"}` raises into, for the guess-inputs-when-stuck story."""


def parse(s: str) -> int:
    try:
        value = int(s, 16)
    except ValueError:
        return -1
    return value
