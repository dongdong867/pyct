import json
import os
import subprocess
import sys

from tests.acceptance.harness import REPO_ROOT

WALK = "targets.sweep.walk"
ROUGH = "targets.sweep.rough"


def lister(*argv: str) -> tuple[list[dict[str, object]], str]:
    """The lister's facts for ``argv``, and what it wrote on stderr."""
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-P", "-m", "pyct.sweep.lister", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return [json.loads(line) for line in finished.stdout.splitlines()], finished.stderr


def entry(module: str, name: str, seed: dict[str, object]) -> dict[str, object]:
    return {"entry": {"module": module, "name": name, "seed": seed, "skip": None}}


def test_it_walks_public_modules_in_name_order_and_says_each_fact() -> None:
    facts, said = lister(WALK)

    assert facts == [
        {"importing": WALK},
        {"importing": f"{WALK}.prices"},
        entry(f"{WALK}.prices", "total", {"n": 0}),
        {"importing": f"{WALK}.util"},
        {"importing": f"{WALK}.util.text"},
        entry(f"{WALK}.util.text", "shout", {"s": ""}),
        {"done": True},
    ]
    # a module that prints while it is imported breaks no line: its text went to stderr
    assert "walk.util imported" in said


def test_after_a_module_it_imports_only_the_packages_on_the_way_and_what_comes_next() -> None:
    facts, _ = lister(ROUGH, "--after", f"{ROUGH}.gone")

    assert facts == [
        {"importing": ROUGH},
        {"importing": f"{ROUGH}.prices"},
        entry(f"{ROUGH}.prices", "total", {"n": 0}),
        {"importing": f"{ROUGH}.quits"},
        {"failed": f"{ROUGH}.quits", "reason": "SystemExit(0)"},
        {"importing": f"{ROUGH}.zeta"},
        entry(f"{ROUGH}.zeta", "last", {"n": 0}),
        {"done": True},
    ]


def test_a_package_on_the_way_is_imported_again_and_lists_nothing() -> None:
    facts, _ = lister(WALK, "--after", f"{WALK}.util.text")

    assert facts == [{"importing": WALK}, {"importing": f"{WALK}.util"}, {"done": True}]
