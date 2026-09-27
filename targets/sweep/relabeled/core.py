"""A sweep fixture: a class whose __module__ names the api package, as a library's helper sets
it for what it exports there, though its code is here."""


class Widget:
    def __init__(self, n: int) -> None:
        self.n = n

    def spin(self, times: int) -> int:
        return self.n * times


Widget.__module__ = "targets.sweep.relabeled.api"
