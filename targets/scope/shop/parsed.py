from measure.parse import parse


def parsed(x: int) -> str:
    if parse(x) == 7:
        return "seven"
    return "other"
