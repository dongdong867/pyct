def kept(config: dict[str, int]) -> str:
    ok = bool(config)
    if ok:
        return "filled"
    return "empty"


def changed_before(config: dict[str, int]) -> str:
    config["a"] = 0
    ok = bool(config)
    if ok:
        return "filled"
    return "empty"


def changed_after(config: dict[str, int]) -> str:
    ok = bool(config)
    config["b"] = 1
    if ok:
        return "filled"
    return "empty"


def inside(cfg: dict[str, dict[str, int]]) -> str:
    ok = bool(cfg["a"])
    if ok:
        return "filled"
    return "empty"


def keys(config: dict[str, int]) -> str:
    ok = bool(config.keys())
    if ok:
        return "filled"
    return "empty"


def values(config: dict[str, int]) -> str:
    ok = bool(config.values())
    if ok:
        return "filled"
    return "empty"


def items(config: dict[str, int]) -> str:
    ok = bool(config.items())
    if ok:
        return "filled"
    return "empty"


def stored_outside(config: dict[str, int]) -> str:
    dict.__setitem__(config, "z", 0)
    ok = bool(config)
    if ok:
        return "filled"
    return "empty"


def two_arguments(config: dict[str, int]) -> bool:
    return bool(config, 1)
