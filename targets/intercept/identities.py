def sides(x: int) -> list[str]:
    b = x > 5
    seen = []
    if b is False:
        seen.append("is False")
    if b is not True:
        seen.append("is not True")
    if b is not False:
        seen.append("is not False")
    if True is b:
        seen.append("True is")
    return seen
