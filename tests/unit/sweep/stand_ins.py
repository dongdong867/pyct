"""Stand-ins for the programs a sweep starts, each a Python script run with ``-c``.

``PYCT`` acts as the boot that starts ``pyct run`` would for the entry its target names:
``ran`` and the functions ``f`` and ``h`` print a summary line and exit 0, and the rest end
as their name says. Its summary line holds what it was given, so a test can read the folder
it was handed to import from, the command, and its working directory.
"""

import sys

PYCT_SCRIPT = """
import json, os, sys, time
imports_from = sys.argv.pop(1)
argv = sys.argv[1:]
name = argv[1].partition("::")[2]
lines = {"f": [1, 2], "h": [2, 3]}.get(name, [1])
summary = {
    "stopped": "no fork to flip",
    "inputs": 1,
    "solver": {},
    "misses": [],
    "covered": {"m.py": lines},
    "total": {"m.py": 4},
    "uncovered": {},
    "environment": {},
    "argv": argv,
    "cwd": os.getcwd(),
    "files": os.listdir("."),
    "imports_from": imports_from,
    "cache": os.environ.get("PYCT_CACHE_DIR"),
}
if name == "exits":
    print(json.dumps(summary))
    print("cvc5 crashed\\nsolver failed\\n", file=sys.stderr)
    sys.exit(1)
if name == "silent":
    sys.exit(0)
if name == "crashes":
    print(json.dumps(summary)[:20], flush=True)
    os.kill(os.getpid(), 11)
if name == "prints":
    # the line the test hands over, as the target's own or pyct run's
    print(os.environ["SWEEP_TEST_LINE"])
    sys.exit(0)
if name.startswith("stray"):
    # the target's own line, which only looks like a summary
    print(json.dumps({"stopped": "the target's own status", "covered": 1}))
    sys.exit(0 if name == "stray_then_zero" else 1)
if name == "hangs":
    time.sleep(3600)
print('{"input": 1}')
print(json.dumps(summary))
"""

PYCT: tuple[str, ...] = (sys.executable, "-c", PYCT_SCRIPT)


def lister(*facts: str) -> tuple[str, ...]:
    """A lister that prints ``facts``, one JSON line each, then that it is done."""
    lines = "".join(f"print({fact!r})\n" for fact in facts)
    return (sys.executable, "-c", f"{lines}print('{{\"done\": true}}')\n")
