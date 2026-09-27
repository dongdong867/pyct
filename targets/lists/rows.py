def check(grid: list[list[int]]):
    for row in grid:
        if row and row[0] > 5:
            return "big"
    return "small"
