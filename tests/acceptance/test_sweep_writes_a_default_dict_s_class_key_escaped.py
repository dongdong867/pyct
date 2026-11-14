"""Acceptance tests for sweep-writes-a-default-dict-s-class-key-escaped: a default dict reaches
each entry's ``pyct run`` as the same dict.

Each sweeps a module in a temporary folder whose entries write the value they got, as JSON, to a
file of their own in the folder ``SEEN`` names. An entry with no branch runs once, so its file's
first line is the seed's value as the target got it.
"""

import json
from pathlib import Path

from tests.acceptance.sweeping import row_named, rows, sweep

HELD = """import json
import os


def _seen(name, value):
    with open(os.path.join(os.environ["SEEN"], name), "a") as file:
        file.write(json.dumps(value) + "\\n")


def top(d={"__class__": "plain", "n": 1}):
    _seen("top", d)


def in_a_list(d=[{"__class__": "plain"}]):
    _seen("in_a_list", d)


def in_a_dict(d={"inner": {"__class__": "plain"}}):
    _seen("in_a_dict", d)


def banged(d={"!__class__": "plain", "!!__class__": 2}):
    _seen("banged", d)
"""

# each entry's default for its one parameter d, as the target reads it, and as the seed writes it
DEFAULTS = {
    "top": ({"__class__": "plain", "n": 1}, {"!__class__": "plain", "n": 1}),
    "in_a_list": ([{"__class__": "plain"}], [{"!__class__": "plain"}]),
    "in_a_dict": ({"inner": {"__class__": "plain"}}, {"inner": {"!__class__": "plain"}}),
    "banged": (
        {"!__class__": "plain", "!!__class__": 2},
        {"!!__class__": "plain", "!!!__class__": 2},
    ),
}


def test_each_default_dict_reaches_its_run_as_the_same_dict(tmp_path: Path) -> None:
    (tmp_path / "held.py").write_text(HELD)
    seen = tmp_path / "seen"
    seen.mkdir()
    result = sweep("held", cwd=tmp_path, env={"SEEN": str(seen)})

    assert result.returncode == 0, result.stderr
    assert [row["status"] for row in rows(result.stdout)] == ["ran"] * len(DEFAULTS)
    for name, (default, written) in DEFAULTS.items():
        row = row_named(result.stdout, "held", name)
        assert json.dumps(row["seed"]) == json.dumps({"d": written}), row
        first = (seen / name).read_text().splitlines()[0]
        assert first == json.dumps(default), name
