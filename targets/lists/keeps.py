# a list the first input hands over stays here for the inputs after it, in one process
_KEPT: list[list[int]] = []


def keep(items):
    _KEPT.append(items)
    if _KEPT[0][0] > 5:
        return "big"
    return "small"
