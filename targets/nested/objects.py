"""Objects a seed given through run() holds, and targets that read their attributes."""

import threading


class Box:
    """An object deepcopy refuses, for its lock, with an int beside it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.n = 0


def boxed(box):
    if box.n > 5:
        return "big"
    return "small"
