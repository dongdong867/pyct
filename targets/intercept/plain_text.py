def search(s: str) -> int:
    text = "xyz"
    seen = 0
    if "abc".find(s) == 1:
        seen += 1
    if "abc".rfind(s) == 2:
        seen += 2
    if "abc".count(s) == 1:
        seen += 4
    if "abc".startswith(s):
        seen += 8
    if "abc".endswith(s):
        seen += 16
    if text.find(s) == 0:
        seen += 32
    return seen


def untaught(s: str) -> str:
    if "abcx".find(s, 1) == 3:
        return "found"
    return "other"


def alone(s: str) -> str:
    if "abc".find("b") == 1:
        if s == "q":
            return "q"
    return "other"


def index(s: str) -> int:
    return "abc".index(s)
