"""A module whose every missing name raises something other than AttributeError as it is read."""


def __getattr__(name: str) -> object:
    raise RuntimeError(f"cannot give {name}")
