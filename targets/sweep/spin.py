"""A sweep fixture: a function that forks on its argument on every pass of a loop, so no input
after the first covers a line the first did not, and whose `return -1` no input reaches, so the
plateau, not full coverage, ends the run."""


def spin(n: int) -> int:
    count = 0
    for step in range(100):
        if n == step:
            count += 1
    if count > 1:
        return -1
    return count
