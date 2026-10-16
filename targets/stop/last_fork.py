import time


def flip(x: int):
    if x > 0:
        return 1
    return 0


def stall(x: int):
    if x > 0:
        while True:
            time.sleep(1)
    return 0
