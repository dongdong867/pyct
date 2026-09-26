def parse(x: int) -> int:
    # 1000 digits: over a limit of 640, under Python's default of 4300
    return int("1" * 1000) + x
