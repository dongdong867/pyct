from targets.trace import helper_check


def route(x: int) -> str:
    if helper_check.is_small(x):
        return "small"
    if x < 100:
        return "medium"
    return "big"
