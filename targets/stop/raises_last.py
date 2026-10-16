def check(s: str):
    if s.startswith("long"):
        flag = s.endswith("q") or s.endswith("z")
        raise ValueError(flag)
    return 0
