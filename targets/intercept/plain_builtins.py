def plain(x: int) -> list[str]:
    seen = []
    if len(*["ab"]) == 2:
        seen.append("len")
    if list(map(len, ["a", "bc"])) == [1, 2]:
        seen.append("map")
    if ord("a") == 97:
        seen.append("ord")
    if chr(98) == "b":
        seen.append("chr")
    if x > 0:
        seen.append("x")
    return seen
