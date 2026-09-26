"""What the checker learns about the machine: where cvc5 is and its version, each commit.

Both sides take cvc5 from PATH, so the checker looks there once, before any target runs, and
says what ``pyct run`` says when it finds none.
"""

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

INSTALL = "install it from https://cvc5.github.io/ (brew install cvc5)"

# each probe prints a line and exits; anything slower is not answering
PROBE_SECONDS = 10.0


class SolverMissingError(Exception):
    """cvc5 is not on PATH. The message says where the checker looked and how to install it."""

    def __init__(self, searched: tuple[str, ...]) -> None:
        looked = ", ".join(searched) or "nowhere, PATH is empty"
        super().__init__(f"cvc5 was not found on PATH (looked in: {looked})\n{INSTALL}")


def locate_cvc5(environment: Mapping[str, str]) -> Path:
    """The cvc5 on the environment's PATH."""
    path = environment.get("PATH", "")
    found = shutil.which("cvc5", path=path)
    if found is None:
        raise SolverMissingError(tuple(entry for entry in path.split(os.pathsep) if entry))
    return Path(found)


def cvc5_version(cvc5: Path) -> str | None:
    """The first line ``cvc5 --version`` prints, or ``None`` when it says nothing readable."""
    said = _output([str(cvc5), "--version"])
    return said[0] if said else None


def commit(checkout: Path) -> str | None:
    """The commit checked out at ``checkout``, or ``None`` when it is not a git checkout's root."""
    said = _output(["git", "-C", str(checkout), "rev-parse", "--show-toplevel", "HEAD"])
    if len(said) != 2 or Path(said[0]).resolve() != checkout.resolve():
        return None
    return said[1]


def _output(argv: list[str]) -> list[str]:
    """The non-blank lines ``argv`` prints, or none when it fails to run or exits non-zero."""
    try:
        finished = subprocess.run(
            argv,
            input="",
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if finished.returncode != 0:
        return []
    return [line.strip() for line in finished.stdout.splitlines() if line.strip()]
