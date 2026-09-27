def cut(s: str, t: str) -> str:
    parts = s.rsplit(t)
    if len(parts) > 1:
        return "cut"
    return "whole"
