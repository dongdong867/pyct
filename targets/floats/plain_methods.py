def keep_and_lose(f: float) -> int:
    count = 0
    if f.real > 2.5:
        count += 1
    if f.conjugate() < -1.5:
        count += 1
    f.imag
    f.as_integer_ratio()
    f.hex()
    return count
