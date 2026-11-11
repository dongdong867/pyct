"""Acceptance tests for an-llm-seed-names-an-object-s-class: the LLM's seeds build objects through
the classes the request lists, and a method's ``self`` through its constructor.

The ``run()`` cases answer with a fake ``SeedProvider``; the ``pyct run`` cases point the
provider's base URLs at the stub on localhost, or replay a recording against a closed port.
"""

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pyct.llm.seeds import SEED_FORM, request_text
from pyct.results.record import InputRecord, Source
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.llm_seeds import SeedReply, SeedRequest
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import load_target
from tests.acceptance.fake_seeds import COST, FakeSeeds, replying
from tests.acceptance.harness import input_lines
from tests.acceptance.llm_stub import Stub, closed_port, heads, llm_run, write_recording

M = "targets.llm.shop.models"
GREET = "targets.llm.shop.greet"
CHECK = "targets.llm.plain.check::check"
ANN = {"__class__": f"{M}::Customer", "name": "ann", "age": 30}
BOB = {"__class__": f"{M}::Customer", "name": "bob", "age": 70}


@dataclass
class Watching(FakeSeeds):
    """A fake provider that also keeps, for each ask, whether ``M`` was imported by then."""

    imported: list[bool] = field(default_factory=list)

    def seeds(self, request: SeedRequest) -> SeedReply:
        self.imported.append(M in sys.modules)
        super().seeds(request)
        return SeedReply((), COST)


def asked(spec: str, seed: dict[str, object]) -> tuple[Watching, str]:
    """The provider a run of ``spec`` from ``seed`` asked, and the text its one request sends."""
    provider = Watching(SeedReply((), COST))
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))
    run(load_target(spec), [seed], setup=setup)
    [request] = provider.requests
    return provider, request_text(request)


def run_llm(spec: str, *seeds: object) -> list[InputRecord]:
    """The records of a run of ``spec`` with no seed of the user's, from an LLM reply of
    ``seeds``."""
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=replying(*seeds)))
    return list(run(load_target(spec), [], setup=setup).records)


def at(args: object, *path: object) -> object:
    """The value ``args`` holds at ``path``, each step a key or an index."""
    for step in path:
        assert isinstance(args, dict | list), args
        args = args[step]  # pyrefly: ignore[bad-index]
    return args


def above_60(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 60


def solver_args(records: Sequence[InputRecord]) -> list[object]:
    """The args of each solver record that ran with no failure."""
    return [
        record.args
        for record in records
        if record.source is Source.SOLVER and record.failure is None
    ]


def trace_of(stderr: str, head: str) -> list[str]:
    """The trace lines of the input whose head starts with ``head``, the head first."""
    lines = stderr.splitlines()
    start = next(at for at, line in enumerate(lines) if line.startswith(head))
    rest = heads("\n".join(lines[start + 1 :]))
    end = lines.index(rest[0], start + 1) if rest else len(lines)
    return lines[start:end]


# llm-seeds-name-a-class-builds-and-follows-an-object
def test_an_llm_seed_builds_the_object_its_class_names_and_the_run_follows_it(
    stub: Stub, tmp_path: Path
) -> None:
    stub.reply = json.dumps([{"c": ANN}])

    result = llm_run(stub.port, tmp_path, "--llm", "seeds", target=f"{GREET}::greet")

    assert result.returncode == 0, result.stderr
    first, *rest = input_lines(result.stdout)
    assert (first["args"], first["source"], first["failure"]) == ({"c": ANN}, "llm_seed", None)
    trace = trace_of(result.stderr, "llm seed 1 ")
    assert any("  c['age'] > 60  " in line for line in trace), trace
    assert any(
        line["source"] == "solver"
        and line["failure"] is None
        and at(line["args"], "c", "__class__") == ANN["__class__"]
        and above_60(at(line["args"], "c", "age"))
        for line in rest
    ), rest


# llm-seeds-name-a-class-builds-at-any-depth
def test_an_llm_seed_builds_objects_inside_a_list_and_inside_another_object() -> None:
    crowd = run_llm(f"{GREET}::seniors", {"cs": [ANN, BOB]})
    order = {"__class__": f"{M}::Order", "customer": ANN, "total": 5}
    paid = run_llm(f"{GREET}::pay", {"o": order})

    for records in (crowd, paid):
        assert records[0].source is Source.LLM_SEED
        assert records[0].failure is None, records[0].failure
    assert any(
        above_60(at(args, "cs", 0, "age")) and len(at(args, "cs")) == 2  # pyrefly: ignore
        for args in solver_args(crowd)
    )
    assert any(above_60(at(args, "o", "customer", "age")) for args in solver_args(paid))


# llm-seeds-name-a-class-replays-a-reply-that-names-a-class
def test_a_replayed_reply_that_names_a_class_builds_it(tmp_path: Path) -> None:
    place = f"{GREET}::greet"
    recording = write_recording(
        tmp_path / "recorded.jsonl", [{"place": place, "reply": json.dumps([{"c": ANN}])}]
    )

    result = llm_run(
        closed_port(), tmp_path, "--llm", "seeds", "--llm-replay", str(recording), target=place
    )

    assert result.returncode == 0, result.stderr
    first, *rest = input_lines(result.stdout)
    assert (first["args"], first["source"], first["failure"]) == ({"c": ANN}, "llm_seed", None)
    assert any(
        line["source"] == "solver" and above_60(at(line["args"], "c", "age")) for line in rest
    )


# llm-seeds-name-a-class-the-request-shows-the-class
def test_the_request_shows_the_class_and_its_module_is_not_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, M, raising=False)

    provider, text = asked(f"{GREET}::greet", {"c": 1})

    assert (
        f"# {M}::Customer\nclass Customer:\n    def __init__(self, name, age):\n"
        '        if age < 0:\n            raise ValueError("negative age")\n'
        "        self.name = name\n        self.age = age\n"
    ) in text
    assert '"__class__": "module::QualifiedName"' in text
    assert provider.imported == [False]


# llm-seeds-name-a-class-sends-no-class-list-when-the-folder-has-none
def test_the_request_has_no_classes_section_when_the_folder_defines_no_class() -> None:
    provider, text = asked(CHECK, {"n": 0})

    [request] = provider.requests
    assert request.classes == ""
    assert not [line for line in text.splitlines() if line.startswith("# ") and "::" in line]
    # the code's section, then the user's seed, then the seed form
    assert (
        f'```\n\nThe user\'s seeds, which already run, one per line:\n{{"n": 0}}\n\n{SEED_FORM}'
        in text
    )
    plain = SeedRequest(request.place, request.code, request.signature, request.seeds, request.goal)
    assert text == request_text(plain)


# llm-seeds-build-self-the-request-shows-self-s-constructor
def test_the_request_shows_self_s_constructor_and_how_self_is_written() -> None:
    _, text = asked(f"{M}::Till.total", {"self": {"owner": "x"}, "discount": 0})

    assert "def __init__(self, owner):\n    self.owner = owner" in text
    assert "A method's self is a JSON object of its class's constructor arguments" in text
