import os


def leave(x: int) -> str:
    if x > 3:
        os._exit(3)
    return "stayed"
