def check(x: int) -> str:
    flag = x > 3
    if flag in range(1, 2):
        return "yes"
    return "no"
