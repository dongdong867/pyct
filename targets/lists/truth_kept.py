import heapq


def kept(items: list[int]) -> str:
    ok = bool(items)
    if ok:
        return "filled"
    return "empty"


def changed_before(items: list[int]) -> str:
    items.append(0)
    ok = bool(items)
    if ok:
        return "filled"
    return "empty"


def changed_after(items: list[int]) -> str:
    ok = bool(items)
    items.append(1)
    if ok:
        return "filled"
    return "empty"


def inside(grid: list[list[int]]) -> str:
    ok = bool(grid[0])
    if ok:
        return "filled"
    return "empty"


def pushed(items: list[int]) -> str:
    heapq.heappush(items, 0)
    ok = bool(items)
    if ok:
        return "filled"
    return "empty"


def two_arguments(items: list[int]) -> bool:
    return bool(items, 1)
