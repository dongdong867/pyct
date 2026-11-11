import json

from targets.classes import lazy
from targets.llm import helpers


def outer(x: int) -> str:
    if helpers.sign(x) < 0:
        return json.dumps(middle(x))
    return str(len([x]))


def middle(x: int) -> int:
    if x < -10:
        return len(outer(x + 1))
    return last(x)


def last(x: int) -> int:
    values = [x]
    values.append(lazy.made(x))
    return [len][0](values)


class Counter:
    def __init__(self, start: int) -> None:
        self.start = start

    def bump(self, x: int) -> int:
        if self.step(x) > 10:
            return Counter.twice(x)
        return x

    def step(self, x: int) -> int:
        return x + self.start

    @staticmethod
    def twice(x: int) -> int:
        return 2 * x
