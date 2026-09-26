CALLS = 0


def count(x: int) -> str:
    global CALLS
    CALLS += 1
    seen = False
    if CALLS > 1:
        seen = True  # marked: runs only when an earlier call left the count above 0
    if x > 3:
        return f"big {seen}"
    return f"small {seen}"
