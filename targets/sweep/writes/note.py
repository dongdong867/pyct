"""A sweep fixture: a public function that writes a file when it is called."""

import os
from pathlib import Path


def jot(n: int) -> None:
    Path(os.environ.get("SWEEP_NOTE_FILE", "note.txt")).write_text(str(n))
