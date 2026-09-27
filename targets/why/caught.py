def caught(x: int) -> int:
    try:
        y = 10 // (x - x)
        return y
    except ZeroDivisionError:
        return 0
