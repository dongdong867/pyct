def check_then_count(x: int, y: int) -> str:
    if y > 100:
        return "big"
    while x > 0:
        x -= 1
    return "counted"
