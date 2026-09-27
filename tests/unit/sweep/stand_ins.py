"""Stand-ins for the programs a sweep starts, each a Python script run with ``-c``.

``PYCT`` acts as ``pyct run`` would for the entry its target names: ``ran`` and the
names in ``LINES`` print a summary line and exit 0, and the rest end as their name says.
Its summary line holds what it was given, so a test can read the command and the directory.
"""

import sys

PYCT_SCRIPT = """
import json, os, sys, time
argv = sys.argv[1:]
name = argv[1].partition("::")[2]
lines = {"f": [1, 2], "h": [2, 3]}.get(name, [1])
summary = {
    "stopped": "no fork to flip",
    "covered": {"m.py": lines},
    "total": {"m.py": 4},
    "argv": argv,
    "cwd": os.getcwd(),
    "files": os.listdir("."),
    "path": os.environ.get("PYTHONPATH"),
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
