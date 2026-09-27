"""A sweep fixture: a module whose __getattr__ raises for every name it lacks, __all__ too."""


def __getattr__(name: str) -> object:
    raise RuntimeError(f"{name} is made on first use, and making it failed")


def soon(n: int) -> int:
    return n
