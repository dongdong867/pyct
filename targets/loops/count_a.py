def count_as(s: str) -> str:
    count = 0
    for c in s:
        if c == "a":
            count += 1
    if count > 2:
        return "many"
    return "few"
