def down_from(n: int) -> str:
    for i in range(n, 0, -1):
        if i == 10:
            return "ten"
    return "none"
