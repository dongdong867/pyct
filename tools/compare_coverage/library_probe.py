"""Say which version of a library an interpreter has, and the folder its modules sit in.

Each side's own interpreter runs this file for an installed entry, started as the side is:
``PYTHON -P library_probe.py NAME`` from the entry's root, with the side's environment. It
puts that working directory first on the path, as both sides do before they import a
target, so it finds the library the side imports. It prints one JSON line,
``{"version", "root"}``, both ``null`` when the library is not installed. NAME ``python`` is
the standard library: Python's version, and the folder of its modules.

It imports the standard library only, because it runs in legacy's environment as well as in
this checkout's.
"""

import importlib.metadata
import json
import os
import platform
import sys
import sysconfig


def installed(name: str) -> dict[str, str | None]:
    """The version of the distribution ``name`` and the folder its modules sit in."""
    if name == "python":
        return {"version": platform.python_version(), "root": sysconfig.get_path("stdlib")}
    try:
        found = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return {"version": None, "root": None}
    return {"version": found.version, "root": str(found.locate_file(""))}


def main(argv: list[str]) -> int:
    sys.path.insert(0, os.getcwd())
    print(json.dumps(installed(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
