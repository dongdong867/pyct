class Box:
    def __int__(self) -> int:
        return 1 // 0


def of_box(x: int) -> int:
    return int(Box()) + x


def int_of(s: str) -> int:
    return int(s)


def int_of_float(x: float) -> int:
    return int(x)


def float_of(s: str) -> float:
    return float(s)
