"""A sweep fixture: a function that forks on its argument on every pass of a loop, so no input
after the first covers a line the first did not."""


def spin(n: int) -> int:
    count = 0
    for step in range(100):
        if n == step:
            count += 1
    return count
