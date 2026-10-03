import builtins


def longer(s: str) -> str:
    if builtins.len(s) > 3:
        return "long"
    return "short"
