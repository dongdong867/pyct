import json
import os
import subprocess
import sys
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT

WALK = "targets.sweep.walk"
ROUGH = "targets.sweep.rough"


def lister(*argv: str, cwd: Path = REPO_ROOT) -> tuple[list[dict[str, object]], str]:
    """The lister's facts for ``argv``, and what it wrote on stderr."""
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-P", "-m", "pyct.sweep.lister", *argv],
        cwd=cwd,
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


def test_a_module_whose_name_is_no_identifier_is_not_walked(tmp_path: Path) -> None:
    # pyct run cannot name it, and "-" sorts before ".", out of the order --after relies on
    package = tmp_path / "ph"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "a-b.py").write_text("def hy(n: int) -> int:\n    return n\n")
    (package / "ok.py").write_text("def fine(n: int) -> int:\n    return n\n")

    facts, _ = lister("ph", cwd=tmp_path)

    assert facts == [
        {"importing": "ph"},
        {"importing": "ph.ok"},
        entry("ph.ok", "fine", {"n": 0}),
        {"done": True},
    ]


def test_a_module_whose_getattr_raises_is_read_to_the_end_by_one_lister() -> None:
    # asking a plain module for __path__ must not run its __getattr__, which raises here
    unread = "targets.sweep.unread"
    facts, said = lister(unread)

    lazy = f"{unread}.lazy"
    assert {"importing": lazy} in facts
    assert facts[-1] == {"done": True}, said


def test_a_folder_with_no_init_is_walked_as_a_namespace_package() -> None:
    spaced = "targets.sweep.spaced"
    facts, _ = lister(spaced)

    assert facts == [
        {"importing": spaced},
        {"importing": f"{spaced}.plain"},
        {"importing": f"{spaced}.plain.mod"},
        entry(f"{spaced}.plain.mod", "spread", {"n": 0}),
        {"importing": f"{spaced}.top"},
        entry(f"{spaced}.top", "top", {"n": 0}),
        {"done": True},
    ]
