def lose(x: int) -> int:
    wide = 0
    if x.bit_length() > 8:
        wide = 1
    x.bit_count()
    x.to_bytes(length=2, byteorder="big")
    return wide


def keep(x: int) -> int:
    count = 0
    if x.real > 5:
        count += 1
    if x.numerator > 6:
        count += 1
    if x.conjugate() > 7:
        count += 1
    if x.as_integer_ratio()[0] > 8:
        count += 1
    return count


def read(x: int) -> int:
    count = 0
    if x.imag == 0:
        count += 1
    if x.denominator == 1:
        count += 1
    if x.is_integer():
        count += 1
    return count


def as_its_int(x: int) -> str:
    b = x > 0
    label = "off"
    if b.real == 1:
        label = "on"
    b.bit_length()
    return label


def build(x: int, f: float) -> str:
    y = x.from_bytes(b"\x01\x00", "big")
    z = f.fromhex("0x1p2")
    if y == 256 and z == 4.0:
        return "built"
    return "other"


def overflow(x: int) -> bytes:
    return x.to_bytes(1, "big")
