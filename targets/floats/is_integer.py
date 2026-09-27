def whole(x: float) -> str:
    if x.is_integer():
        return "whole"
    return "fraction"
