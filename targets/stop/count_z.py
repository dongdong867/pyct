def test(s: str):
    t = 0
    while s != "":
        if "z" in s:
            t += 1
        s = s[:-1]
    if t > 5:
        return "medium"
    return "small"
