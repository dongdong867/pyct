"""A sweep fixture: a module that imports cleanly the first time and reads memory at address
zero every later time, in any process.

It counts its imports in the file SWEEP_IMPORTS_FILE names; with the variable unset it always
imports cleanly.
"""

import ctypes
import os

imports = os.environ.get("SWEEP_IMPORTS_FILE")
if imports:
    with open(imports, "a+") as file:
        file.seek(0)
        before = file.read()
        file.write("x")
    if before:
        ctypes.string_at(0)  # reads memory at address zero


def price(n: int) -> int:
    if n > 0:
        return n
    return 0
