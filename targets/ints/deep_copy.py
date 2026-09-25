import copy


def check(n: int) -> str:
    backup = copy.deepcopy({"n": n})
    if backup["n"] > 10:
        return "big"
    return "small"
