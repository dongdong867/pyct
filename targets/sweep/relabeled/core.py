"""A sweep fixture: classes whose __module__ names the api package, as a library's helper sets
it for what it exports there, though their code is here."""

import functools


class Widget:
    def __init__(self, n: int) -> None:
        self.n = n

    def spin(self, times: int) -> int:
        return self.n * times


class Gadget(Widget):
    @property
    def size(self) -> int:
        return self.n


class Meter(Widget):
    @functools.cached_property
    def reading(self) -> int:
        return self.n


Widget.__module__ = "targets.sweep.relabeled.api"
Gadget.__module__ = "targets.sweep.relabeled.api"
Meter.__module__ = "targets.sweep.relabeled.api"
