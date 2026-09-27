def lose(x: int) -> int:
    b = x > 0
    ~b
    b << 1
    b & 3
    int(b)
    if str(b) == "True" and f"{b}" == "True":
        if b:
            return 1
    return 0
