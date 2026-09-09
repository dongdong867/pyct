from targets.trace import helper_check


def route(x: int) -> str:
    if x < 100:
        return "huge"
    if helper_check.is_small(x):
        return "small"
    return "big"
