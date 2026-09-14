"""Where the cvc5 executable is, what version it is, and what to tell a person without one."""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL = "install it from https://cvc5.github.io/ (brew install cvc5)"

# the probe prints one line and exits, so anything slower is a cvc5 that is not answering
PROBE_SECONDS = 5.0

# what a version number looks like at the start of a token, so ``1.1.3-dev.196`` keeps its tail
NUMBER = re.compile(r"\d+\.\d+(\.\d+)?")


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


def version(cvc5: Path) -> str | None:
    """What ``cvc5 --version`` reports, or ``None`` when the probe gave nothing readable.

    The version is a nicety on the summary line, so every way the probe can
    go wrong is a warning and a ``None`` rather than an error: a run is never
    stopped by not knowing which cvc5 answered it.
    """
    try:
        # nothing is written to stdin, so a cvc5 that reads it finds the end at once
        finished = subprocess.run(
            [str(cvc5), "--version"],
            input="",
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("could not ask %s for its version: %s", cvc5, error)
        return None
    if finished.returncode != 0:
        logger.warning("%s --version exited %d", cvc5, finished.returncode)
        return None
    return _reported(finished.stdout)


def _reported(printed: str) -> str | None:
    """The first token that starts with a number, on the first line that says anything.

    1.2.x writes ``This is cvc5 version 1.2.1 [...]`` and 1.3.x writes
    ``cvc5 1.3.4 [...]``, so the number is found by its own shape rather
    than by what sits in front of it. A line naming no number is kept
    whole rather than guessed at.
    """
    said = [line.strip() for line in printed.splitlines() if line.strip()]
    if not said:
        logger.warning("cvc5 --version printed nothing")
        return None
    numbered = [word for word in said[0].split() if NUMBER.match(word)]
    return numbered[0] if numbered else said[0]
