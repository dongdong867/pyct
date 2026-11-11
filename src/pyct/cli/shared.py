"""What both commands use: the parser that raises instead of exiting, and one stdout line."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from pyct.config.command_line import UsageError


class Parser(argparse.ArgumentParser):
    """An argparse parser that raises UsageError instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{message}\nusage: {self.usage}")


def line(text: str) -> None:
    """One stdout line: the text and its end go out in one write, so a Ctrl-C between two
    writes cannot leave the line without its end."""
    sys.stdout.write(f"{text}\n")
    sys.stdout.flush()
