def field(n: int) -> str:
    if n & 1:
        return "odd"
    if n >> 4 == 3:
        return "x"
    return "other"


def each_operator(n: int) -> str:
    if 0xF0 & n == 0x30:
        return "high nibble"
    if n | 1 == -1:
        return "minus one or two"
    if n ^ -8 == 5:
        return "flipped"
    if ~n == 100:
        return "inverted"
    n <<= 3
    if n == 8:
        return "shifted"
    return "other"


def two_masks(x: int, y: int) -> str:
    if x & y == 12 and x > 100 and y > 100:
        return "shared"
    if x ^ y == 5:
        return "apart"
    return "other"


def still_lost(n: int, b: bool) -> str:
    if 1 << n == 8:
        return "eight"
    if b << 1 == 2:
        return "true"
    return "other"


def negative_count(n: int) -> int:
    return n << -1
