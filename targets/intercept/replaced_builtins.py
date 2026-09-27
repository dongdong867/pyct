import builtins
import sys

_PYTHON = {"ord": builtins.ord, "len": builtins.len, "chr": builtins.chr}


def _logged(name: str, calls: list[str]):
    python = _PYTHON[name]

    def logged(value):
        # only the calls `replaced` makes: whatever else runs in the process may call it too
        if sys._getframe(1).f_code.co_name == "replaced":
            calls.append(name)
        return python(value)

    return logged


def replaced(s: str) -> str:
    calls: list[str] = []
    for name in _PYTHON:
        setattr(builtins, name, _logged(name, calls))
    try:
        ord(s[0]), len(s), chr(65)
    finally:
        for name, python in _PYTHON.items():
            setattr(builtins, name, python)
    # plain Python calls what builtins holds when the call runs: each replacement once
    if calls == ["ord", "len", "chr"]:
        return "replaced"
    return "bound"
