def check(grid: list[list[int]]):
    for row in grid:
        if row and row[0] > 5:
            return "big"
    return "small"


def last_row(grid):
    last = grid[-1]
    if last and last[0] > 5:
        return "big"
    for row in grid:
        pass
    return "end"


def row_at(grid, i):
    if grid[i][0] > 5:
        return "big"
    return "small"
