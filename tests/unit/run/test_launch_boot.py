"""The boot of a command's process started fresh: pyct from its own folder, and nothing else.

The boot puts the folder that holds pyct first on the path to import the pyct package. The
modules the command line then imports, the standard library's among them, come from where the
interpreter finds them, not from that folder, which for an installed pyct is site-packages.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from pyct.core.branch import PYCT_ROOT
from pyct.run.launch import _BOOT

# a module named as one the command line imports, which says so and raises when imported
RAISING_ARGPARSE = "import sys\nsys.stderr.write('SHADOW argparse\\n')\nraise RuntimeError\n"


def test_the_command_line_imports_past_pyct_s_own_folder(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "pyct").symlink_to(Path(PYCT_ROOT) / "pyct")
    (root / "argparse.py").write_text(RAISING_ARGPARSE)
    path = [entry for entry in sys.path if isinstance(entry, str)]
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    # pyct run with no target is a usage error, once the command line has imported
    booted = subprocess.run(
        [sys.executable, "-P", "-c", _BOOT, str(root), json.dumps(path), "run"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert booted.returncode == 2, booted.stderr
    assert "SHADOW" not in booted.stderr
