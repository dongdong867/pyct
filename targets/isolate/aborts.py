import os


def give_up(x: int) -> str:
    if x > 3:
        os.abort()
    return "kept going"
