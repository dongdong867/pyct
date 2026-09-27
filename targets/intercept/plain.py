def plain(n: int) -> list[str]:
    k = 3
    seen = []
    if True is True:
        seen.append("true is true")
    if k is not False:
        seen.append("k is not false")
    if 1 in {1, 2}:
        seen.append("one in a set")
    if "b" in "abc":
        seen.append("b in abc")
    if 3 not in [1, 2]:
        seen.append("three not in a list")
    if "k" in {"k": 1}:
        seen.append("k in a dict")
    if n > 0:
        seen.append("n")
    return seen
