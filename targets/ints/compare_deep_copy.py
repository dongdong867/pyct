import copy


def check(n: int) -> str:
    saved = copy.deepcopy({"big": n > 10})
    if saved["big"]:
        return "big"
    return "small"
