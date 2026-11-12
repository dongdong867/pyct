"""run() asks a SeedProvider once, before the first input, and runs the seeds that pass the checks
after the user's own, with the budget's clock paused while it waits."""

import importlib
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import pytest

from pyct.binding import libraries
from pyct.config.budget import Budget
from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.coverage import Coverage
from pyct.results.llm_asks import Unanswered, Why
from pyct.results.record import InputRecord, Source, StopKind
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.llm_seeds import NoSeedError, SeedReply
from pyct.run.notes import AskSkipped, Note, ReplyIgnored, SeedDropped, SeedsKept
from pyct.run.run import run
from pyct.run.seed_checks import SeedCheck
from pyct.run.setup import Setup
from pyct.run.target import load_target
from pyct.run.tell import Tell
from tests.acceptance.fake_seeds import COST, FakeSeeds, replying

# `f(x: int)`: `if x == 1234:` guards `return 1`, then it calls `sign` in targets.llm.helpers
F = "targets.llm.seeds::f"
# `hang(x: int)`: never returns, so every run ends on its budget
HANG = "targets.isolate.hangs_with_finally::hang"
NO_LIMITS = Limits()


def deep(value: object, levels: int) -> object:
    for _ in range(levels):
        value = [value]
    return value


@dataclass
class Heard:
    notes: list[Note] = field(default_factory=list)
    records: list[InputRecord] = field(default_factory=list)


def run_f(
    provider: FakeSeeds,
    seeds: Sequence[dict[str, object]] = ({"x": 0},),
    limits: Limits = NO_LIMITS,
) -> tuple[list[InputRecord], Heard]:
    heard = Heard()

    def report(record: InputRecord, _coverage: Coverage) -> None:
        heard.records.append(record)
        provider.reported.append(record)

    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))
    tell = Tell(report=report, noted=heard.notes.append)
    result = run(load_target(F), list(seeds), limits=limits, setup=setup, tell=tell)
    return list(result.records), heard


def args_and_sources(records: Sequence[InputRecord]) -> list[tuple[object, Source]]:
    return [(record.args, record.source) for record in records]


# llm-seeds-at-start-runs-after-the-user-s-seeds
def test_the_llm_s_seeds_run_after_the_user_s_and_before_any_solver_input() -> None:
    records, heard = run_f(replying({"x": 1234}, {"x": 7}))

    assert args_and_sources(records[:3]) == [
        ({"x": 0}, Source.SEED),
        ({"x": 1234}, Source.LLM_SEED),
        ({"x": 7}, Source.LLM_SEED),
    ]
    assert all(record.source is Source.SOLVER for record in records[3:])
    assert heard.notes == [SeedsKept((1, 2))]


# llm-seeds-at-start-asks-once-before-any-input
def test_the_provider_is_asked_once_before_the_first_input_runs() -> None:
    provider = replying({"x": 7})

    run_f(provider)

    assert len(provider.requests) == 1
    assert provider.reported_before == [0]


# llm-seeds-at-start-sends-the-code-and-the-seeds
def test_the_request_holds_the_code_its_callee_the_signature_the_seeds_and_the_goal() -> None:
    provider = replying({"x": 7})

    run_f(provider)

    request = provider.requests[0]
    assert request.place == F
    assert "def f(x: int):" in request.code
    assert "def sign(x: int) -> int:" in request.code
    assert request.signature == "(x: int)"
    assert request.seeds == ('{"x": 0}',)
    assert request.goal is Goal.COVERAGE


def test_the_request_leaves_out_a_seed_over_its_size_and_holds_at_most_ten() -> None:
    provider = replying({"x": 7})
    target = load_target("targets.flip.no_check::echo")
    many = [{"x": n} for n in range(12)]
    big = {"x": "a" * 2_001}
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))

    run(target, [big, *many], setup=setup)

    assert provider.requests[0].seeds == tuple(json.dumps(seed) for seed in many[:10])


# llm-seeds-at-start-wait-is-not-budget-time
def test_the_wait_for_the_seeds_does_not_count_toward_the_budget() -> None:
    provider = replying({"x": 1}, delay=3)
    setup = Setup(helpers=Helpers(seeds=provider))
    started = time.monotonic()

    result = run(load_target(HANG), {"x": 0}, limits=Limits(budget=Budget(4)), setup=setup)

    took = time.monotonic() - started
    assert result.stopped.kind is StopKind.BUDGET
    # the 4 s budget and the 3 s wait; the upper bound only catches a run that overruns both
    assert 6.5 < took < 15, took


# llm-seed-dropped-fails-a-check
def test_a_seed_that_fails_a_check_is_dropped_with_the_check_s_reason() -> None:
    records, heard = run_f(replying({"y": 1}, {"x": "a"}, {"x": 2}))

    check = SeedCheck.of(load_target(F))
    names = "; ".join(check.read('{"y": 1}')[1])
    types = "; ".join(check.read('{"x": "a"}')[1])
    assert heard.notes == [SeedDropped(1, names), SeedDropped(2, types), SeedsKept((3,))]
    assert args_and_sources(records[:2]) == [({"x": 0}, Source.SEED), ({"x": 2}, Source.LLM_SEED)]
    assert records[2].source is not Source.LLM_SEED


def test_a_seed_that_is_no_json_object_is_dropped_with_the_shape_check_s_reason() -> None:
    provider = FakeSeeds(SeedReply(("[1, 2]", '{"x": 3}'), COST))

    _, heard = run_f(provider)

    assert heard.notes == [
        SeedDropped(1, "args must be a JSON object, got list"),
        SeedsKept((2,)),
    ]


# llm-seed-dropped-repeats-a-seed
def test_a_seed_that_repeats_an_earlier_one_is_dropped_naming_that_input() -> None:
    records, heard = run_f(replying({"x": 0}, {"x": 5}, {"x": 5}))

    assert heard.notes == [
        SeedDropped(1, "same seed as input 1"),
        SeedDropped(3, "same seed as input 2"),
        SeedsKept((2,)),
    ]
    assert [record.args for record in records].count({"x": 5}) == 1


def test_a_repeat_of_a_user_s_seed_given_twice_names_its_first_input() -> None:
    _, heard = run_f(replying({"x": 5}, {"x": 5}, {"x": 0}), seeds=[{"x": 0}, {"x": 0}, {"x": 1}])

    # the user's three seeds are inputs 1 to 3 and the LLM's first is input 4
    assert heard.notes == [
        SeedDropped(2, "same seed as input 4"),
        SeedDropped(3, "same seed as input 1"),
        SeedsKept((1,)),
    ]


# where each seed below names tabnanny's class, and the line its drop says
NAG = '"tabnanny::NannyNag"'
LIBRARY = "must name a class of the user's own code, got"
UNLISTED = "must name a class the request listed or one already imported, got"


@pytest.mark.parametrize(
    ("seed", "place"),
    [
        ({"x": {"__class__": "tabnanny::NannyNag"}}, "x"),
        ({"x": [1, {"y": {"__class__": "tabnanny::NannyNag"}}]}, "x[1]['y']"),
        ({"x": deep({"__class__": "tabnanny::NannyNag"}, 600)}, "x" + "[0]" * 600),
    ],
    ids=["top", "nested", "deep"],
)
def test_an_llm_seed_naming_a_standard_library_class_is_dropped_before_its_module_is_imported(
    seed: dict[str, object], place: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "tabnanny", raising=False)

    _, heard = run_f(replying(seed, {"x": 2}))

    assert heard.notes == [
        SeedDropped(1, f"{place}['__class__'] {LIBRARY} {NAG}"),
        SeedsKept((2,)),
    ]
    assert "tabnanny" not in sys.modules


def test_an_installed_distribution_s_module_is_refused_without_importing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = tmp_path / "lib" / "site-packages"
    (installed / "acme_installed").mkdir(parents=True)
    (installed / "acme_installed" / "__init__.py").write_text("raise RuntimeError('imported')\n")
    monkeypatch.syspath_prepend(str(installed))
    roots = (*libraries.LIBRARY_ROOTS, os.path.join(str(installed), ""))
    monkeypatch.setattr(libraries, "LIBRARY_ROOTS", roots)
    before = set(sys.modules)
    named = "acme_installed.models::Thing"

    _, heard = run_f(replying({"x": {"__class__": named}}, {"x": 2}))

    assert heard.notes == [SeedDropped(1, f"x['__class__'] {LIBRARY} \"{named}\""), SeedsKept((2,))]
    assert not {name for name in sys.modules if name.startswith("acme_installed")}
    assert set(sys.modules) - before <= {name for name in sys.modules if name.startswith("targets")}


@pytest.mark.parametrize("named", ["pyct.run.setup::Setup", "__main__::Thing"])
def test_pyct_s_own_module_and_main_are_not_the_user_s_code(named: str) -> None:
    _, heard = run_f(replying({"x": {"__class__": named}}, {"x": 2}))

    assert heard.notes == [SeedDropped(1, f"x['__class__'] {LIBRARY} \"{named}\""), SeedsKept((2,))]


def test_a_user_module_the_request_did_not_list_is_refused_without_importing_it() -> None:
    named = "targets.classes.orders::Buyer"

    _, heard = run_f(replying({"x": {"__class__": named}}, {"x": 2}))

    assert heard.notes == [
        SeedDropped(1, f"x['__class__'] {UNLISTED} \"{named}\""),
        SeedsKept((2,)),
    ]
    assert "targets.classes.orders" not in sys.modules


def test_each_refused_class_of_a_seed_has_its_line_joined_by_semicolons() -> None:
    seed = {
        "x": [{"__class__": "tabnanny::NannyNag"}, {"__class__": "targets.classes.orders::Buyer"}]
    }

    _, heard = run_f(replying(seed, {"x": 2}))

    lines = [
        f"x[0]['__class__'] {LIBRARY} {NAG}",
        f"x[1]['__class__'] {UNLISTED} \"targets.classes.orders::Buyer\"",
    ]
    assert heard.notes == [SeedDropped(1, "; ".join(lines)), SeedsKept((2,))]


@pytest.mark.parametrize(
    "form",
    # the folder's class the request listed, and a class of a module the test already imported
    [
        {"__class__": "targets.llm.calls::Counter", "start": 1},
        {"__class__": "tests.unit.binding.named_classes::Point", "x": 1, "y": 2},
    ],
    ids=["listed", "loaded"],
)
def test_a_listed_module_s_class_or_a_loaded_user_module_s_passes(form: dict[str, object]) -> None:
    importlib.import_module("tests.unit.binding.named_classes")

    _, heard = run_f(replying({"x": form}))

    assert heard.notes[0] == SeedsKept((1,))


def test_a_class_named_through_a_module_a_listed_module_imports_is_refused() -> None:
    named = "targets.llm.calls::json.JSONDecoder"

    _, heard = run_f(replying({"x": {"__class__": named}}, {"x": 2}))

    said = f"x['__class__'] must not step through a module, got \"{named}\""
    assert heard.notes == [SeedDropped(1, said), SeedsKept((2,))]


# llm-seed-dropped-past-the-fifth
def test_the_seeds_past_the_fifth_are_dropped() -> None:
    records, heard = run_f(replying(*({"x": n} for n in range(10, 17))))

    assert heard.notes == [
        SeedDropped(6, "more than 5 seeds"),
        SeedDropped(7, "more than 5 seeds"),
        SeedsKept((1, 2, 3, 4, 5)),
    ]
    assert [record.args["x"] for record in records[1:6]] == [10, 11, 12, 13, 14]


def test_an_ask_with_no_reply_is_said_and_the_run_goes_on_from_the_user_s_seeds() -> None:
    provider = FakeSeeds(Unanswered(Why.TIMED_OUT, "no reply in 30 s", COST))

    records, heard = run_f(provider)

    assert heard.notes == [AskSkipped("seeds", "no reply in 30 s")]
    assert records[0].source is Source.SEED
    assert all(record.source is not Source.LLM_SEED for record in records)


def test_a_reply_the_tool_could_not_read_is_said_and_the_run_goes_on() -> None:
    provider = FakeSeeds(SeedReply((), COST, ignored="no JSON array pyct can read in the reply"))

    records, heard = run_f(provider)

    assert heard.notes == [ReplyIgnored("seeds", "no JSON array pyct can read in the reply")]
    assert records[0].args == {"x": 0}


def test_a_reply_with_no_seed_is_said_and_the_run_goes_on() -> None:
    records, heard = run_f(FakeSeeds(SeedReply((), COST)))

    assert heard.notes == [ReplyIgnored("seeds", "the reply held no seed")]
    assert records[0].args == {"x": 0}


def test_a_user_s_seed_json_cannot_write_runs_and_is_not_quoted() -> None:
    provider = replying({"x": 7})
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))

    result = run(load_target("targets.flip.no_check::echo"), [{"x": Fraction(1, 2)}], setup=setup)

    assert provider.requests[0].seeds == ()
    assert result.records[0].source is Source.SEED


def test_the_plateau_leaves_out_the_llm_s_seeds_too() -> None:
    records, _ = run_f(
        replying({"x": 1}, {"x": 2}, {"x": 3}), limits=Limits(plateau=Plateau(inputs=1))
    )

    # the plateau counts from after the last seed, the LLM's included, so all four run
    assert [record.source for record in records[:4]] == [Source.SEED] + [Source.LLM_SEED] * 3


# llm-seeds-no-seed-refused-none-pass
def test_a_run_with_no_seed_of_its_own_and_none_that_pass_is_refused() -> None:
    provider = replying({"y": 1})
    heard = Heard()
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=provider))
    tell = Tell(report=lambda record, _: heard.records.append(record), noted=heard.notes.append)

    with pytest.raises(NoSeedError) as refused:
        run(load_target(F), [], setup=setup, tell=tell)

    assert refused.value.reason == "every seed was dropped"
    assert [type(note) for note in heard.notes] == [SeedDropped]
    assert heard.records == []


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (Unanswered(Why.TIMED_OUT, "no reply in 30 s", COST), "no reply in 30 s"),
        (
            SeedReply((), COST, ignored="no JSON array pyct can read in the reply"),
            "no JSON array pyct can read in the reply",
        ),
        (SeedReply((), COST), "the reply held no seed"),
    ],
)
def test_a_run_with_no_seed_of_its_own_names_why_the_llm_gave_none(
    answer: SeedReply | Unanswered, reason: str
) -> None:
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=FakeSeeds(answer)))

    with pytest.raises(NoSeedError) as refused:
        run(load_target(F), [], setup=setup)

    assert refused.value.reason == reason


def test_a_run_with_no_seed_of_its_own_starts_from_the_llm_s() -> None:
    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(seeds=replying({"x": 1234})))

    result = run(load_target(F), [], setup=setup)

    assert args_and_sources(result.records[:1]) == [({"x": 1234}, Source.LLM_SEED)]


def test_a_run_with_no_seed_and_no_seeds_helper_is_still_refused() -> None:
    with pytest.raises(ValueError, match="at least one seed"):
        run(load_target(F), [], setup=Setup(isolation=Isolation.IN_PROCESS))
