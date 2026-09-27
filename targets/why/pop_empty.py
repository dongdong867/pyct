def pop_empty(items: list[int]) -> int:
    if items:
        return 0
    v = items.pop()
    return v
