"""A sweep fixture: three functions whose every call sleeps for a minute."""

import time


def a(n: int) -> None:
    time.sleep(60)


def b(n: int) -> None:
    time.sleep(60)


def c(n: int) -> None:
    time.sleep(60)
