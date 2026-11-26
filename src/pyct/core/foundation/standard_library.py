"""Whether a file or folder is Python's standard library's: under the folder its own files lie
in, and not under a folder of installed packages, as a system Python's site-packages inside it is,
or code frozen into the interpreter. pyct's own imports (`pyct.run.own_imports`) look there, and
a loss site in use's plain copy (`pyct.core.entry.plain_copy`) trusts a key's hash whose code lies
there."""

from __future__ import annotations

import functools
import os
import sys


def installed_folders() -> tuple[str, ...]:
    """The folders ``site`` looks in for installed packages, each with a separator on its end.

    One can lie inside the standard library's folder, as a system Python's
    own site-packages does. They are read from ``site`` itself, which
    imports nothing to answer; none when Python started without ``site``,
    as ``-S`` has it, which then puts none of them on the path. Each is
    named as its links lead.
    """
    site = sys.modules.get("site")
    if site is None:
        return ()
    folders = [*site.getsitepackages(), site.getusersitepackages()]
    return tuple(f"{os.path.realpath(folder)}{os.sep}" for folder in folders)


# the folder the standard library's own files lie in, lib-dynload's included, as its links lead,
# with a separator on its end; read from os, which every interpreter has imported, so reading it
# imports nothing
STANDARD = f"{os.path.realpath(os.path.dirname(os.__file__))}{os.sep}"
INSTALLED = installed_folders()
# how the file name of code frozen into the interpreter starts, the import system's included
FROZEN = "<frozen "


@functools.cache
def standard(path: str) -> bool:
    """Whether the file or folder is the standard library's, as its links lead.

    Code frozen into the interpreter is; any other name in angle brackets,
    such as ``<string>``, names no file and is not.
    """
    if path.startswith("<"):
        return path.startswith(FROZEN)
    resolved = f"{os.path.realpath(path)}{os.sep}"
    return resolved.startswith(STANDARD) and not resolved.startswith(INSTALLED)
