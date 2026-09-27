"""A sweep fixture: functions sweep cannot give a seed."""


class Loader:
    pass


def main() -> None:
    return None


def only(*args, **kwargs) -> int:
    return len(args) + len(kwargs)


def later(*, loader=Loader()) -> object:
    return loader


def load(data: bytes) -> int:
    return len(data)


def pair(t: tuple[int, int]) -> int:
    return t[0]


def odd(x):
    return x


odd.__signature__ = 5
