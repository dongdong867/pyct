"""Say which version of a library an interpreter has, where it sits, and if it has a module.

Each side's own interpreter runs this file for an installed entry, started as the side is:
``PYTHON -P library_probe.py NAME MODULE`` from the entry's root, with the side's
environment. It puts that working directory first on the path, as both sides do before they
import a target, so it finds the library the side imports. It prints one JSON line,
``{"version", "root", "provides"}``: ``provides`` is true when the library's record of the
files it installed holds MODULE's file, and ``version`` and ``root`` are ``null`` when the
library is not installed. NAME ``python`` is the standard library: Python's version, and
the folder of its modules, which provides MODULE when MODULE's file is there.

It imports the standard library only, because it runs in legacy's environment as well as in
this checkout's.
"""

import importlib.metadata
import json
import os
import platform
import sys
import sysconfig


def installed(name: str, module: str) -> dict[str, object]:
    """The version of the distribution ``name``, the folder its modules sit in, and whether it
    installed ``module``'s file."""
    if name == "python":
        root = sysconfig.get_path("stdlib")
        provides = any(os.path.isfile(os.path.join(root, path)) for path in _files(module))
        return {"version": platform.python_version(), "root": root, "provides": provides}
    try:
        found = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return {"version": None, "root": None, "provides": False}
    recorded = {str(path) for path in found.files or ()}
    provides = any(path in recorded for path in _files(module))
    return {"version": found.version, "root": str(found.locate_file("")), "provides": provides}


def _files(module: str) -> tuple[str, str]:
    """Where ``module``'s file sits under a library's folder: a module, or a package."""
    base = module.replace(".", "/")
    return f"{base}.py", f"{base}/__init__.py"


def main(argv: list[str]) -> int:
    sys.path.insert(0, os.getcwd())
    print(json.dumps(installed(argv[1], argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
