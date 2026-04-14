from __future__ import annotations

import logging
from typing import Any

SMTLIB2_LEVEL = 17  # Between DEBUG(10) and INFO(20)


def configure_logging(verbose: int, logfile: str | None = None) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        verbose: Logging verbosity (0-3)
        logfile: Path to log file, or empty string for no output
    """
    log_level = 25 - 5 * verbose

    if logfile:
        logging.basicConfig(
            filename=logfile,
            level=log_level,
            format="%(levelname)s\t %(message)s",
            datefmt="%m/%d/%Y %I:%M:%S %p",
        )
    elif logfile == "":
        logging.basicConfig(level=logging.CRITICAL + 1)
    else:
        logging.basicConfig(
            level=log_level,
            format="%(levelname)s\t %(message)s",
        )

    _add_smtlib2_level()


def _add_smtlib2_level() -> None:
    """Add custom SMTLIB2 logging level."""
    logging.addLevelName(SMTLIB2_LEVEL, "SMTLIB2")

    def smtlib2(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a message at the SMTLIB2 level."""
        if self.isEnabledFor(SMTLIB2_LEVEL):
            self._log(SMTLIB2_LEVEL, message, args, **kwargs)

    logging.Logger.smtlib2 = smtlib2
