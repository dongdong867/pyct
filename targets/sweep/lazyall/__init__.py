"""A sweep fixture: a package whose public name loads its module on first access (PEP 562)."""

import importlib

__all__ = ["compute"]


def __getattr__(name: str) -> object:
    if name == "compute":
        return importlib.import_module("._impl", __name__).compute
    raise AttributeError(name)
