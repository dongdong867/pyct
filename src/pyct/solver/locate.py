"""Where the cvc5 executable is, or what to tell a person who has not installed it."""

import os
import shutil
from pathlib import Path

INSTALL = "install it from https://cvc5.github.io/ (brew install cvc5)"


class SolverMissingError(Exception):
    """cvc5 is not on PATH. Nothing can be solved, so the message says where pyct looked."""

    def __init__(self, searched: tuple[str, ...]) -> None:
        looked = ", ".join(searched) or "nowhere, PATH is empty"
        super().__init__(f"cvc5 was not found on PATH (looked in: {looked})\n{INSTALL}")
        self.searched: tuple[str, ...] = searched


def locate() -> Path:
    """The cvc5 on PATH. Every run needs one, so a miss is an error rather than a None."""
    found = shutil.which("cvc5")
    if found is None:
        raise SolverMissingError(_searched())
    return Path(found)


def _searched() -> tuple[str, ...]:
    """The PATH entries pyct looked in. An empty entry means the working directory, not a place."""
    return tuple(entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry)
