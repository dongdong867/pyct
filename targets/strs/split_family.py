def route(s: str) -> str:
    if s.split()[0] == "GET":
        return "split"
    if s.split(",", 1)[1] == "b,c":
        return "maxsplit"
    if s.rsplit("/", 1)[0] == "x/y":
        return "rsplit"
    if s.partition("=")[2] == "on":
        return "partition"
    if s.splitlines()[0] == "top":
        return "splitlines"
    return "other"
