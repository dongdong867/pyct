import ctypes


def fault(x: int, y: int) -> str:
    if y > 3:
        return "tall"
    if x == 7:
        ctypes.string_at(0)  # crashes: reads memory at address zero
    return "short"
