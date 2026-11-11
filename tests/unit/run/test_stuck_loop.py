"""The loop holds a stuck moment on either rule, at most 3 that ask, and a tool's input there
joins the run as any input does."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pyct.binding.bind import Seed
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Reason, Tries, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.record import Source, Stop, StopKind
from pyct.run.bounds import Bounds
from pyct.run.isolation import Inputs, Isolation
from pyct.run.loop import Loop, Looped, Start
from pyct.run.process import InputStartError
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Stuck
from pyct.run.target import load_target
from pyct.run.tell import Tell, Told

# `parse(x)`: no fork at all, and its handler's lines never run
HANDLER = "targets.why.handler::parse"
# `counts(s)`: a loop counts the "z"s, and no fork reads the count; after the third input no
# input covers a new line
COUNTS = "targets.why.stuck::counts"
# `narrow(x)`: x < 5, then x < 10 under it
IMPLIED = "targets.flip.implied_check::narrow"

NO_LIMITS = Limits()


@dataclass
class Tool:
    """A tool that notes each moment it is handed, and may run one input at each."""

    kind: Kind
    asks: bool = True
    runs: Mapping[str, object] | None = None
    pauses: float = 0.0
    moments: list[tuple[int, int, tuple[WhyEntry, ...]]] = field(default_factory=list)
    ran: list[object] = field(default_factory=list)

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        self.moments.append((moment.number, len(moment.run.records), entries))
        if self.pauses:
            moment.run.pause(self.pauses)
        if self.runs is not None:
            self.ran.append(moment.run.run_input(Seed.of(self.runs), Source.LLM_SEED))
        return Handled(tuple(Outcome.TOOK for _ in entries), asked=self.asks)


def loop_of(
    spec: str,
    tools: list[Tool],
    limits: Limits = NO_LIMITS,
    call: Callable[..., object] | None = None,
) -> Loop:
    target = load_target(spec)
    told = Told(scope=Scope.of_module(target.file), tell=Tell(), imported=target.import_lines)
    inputs = call or Inputs(target, Isolation.IN_PROCESS)
    return Loop(inputs, Bounds.of(limits, 1), told, Stuck(tools))  # pyrefly: ignore[bad-argument-type]


def go(loop: Loop, *seeds: Mapping[str, object]) -> Looped:
    return loop.go([Start(Seed.of(seed)) for seed in seeds])


def test_a_run_with_no_fork_left_and_a_line_missed_is_stuck() -> None:
    guesses = Tool(Kind.GUESSES)

    looped = go(loop_of(HANDLER, [guesses]), {"x": 1})

    # one moment: none comes again until an input runs after it
    [(number, inputs, entries)] = guesses.moments
    assert (number, inputs) == (1, 1)
    assert [(entry.lines, entry.reason) for entry in entries] == [((4, 5), Reason.HANDLER)]
    assert looped.stop == Stop(StopKind.NO_FORK)


def test_no_moment_comes_while_a_seed_waits() -> None:
    guesses = Tool(Kind.GUESSES)

    go(loop_of(HANDLER, [guesses]), {"x": 1}, {"x": 2})

    assert [inputs for _, inputs, _ in guesses.moments] == [2]


def test_a_tool_s_input_joins_the_run() -> None:
    guesses = Tool(Kind.GUESSES, runs={"x": 7})

    looped = go(loop_of(HANDLER, [guesses]), {"x": 1})

    assert [(record.args, record.source) for record in looped.records] == [
        ({"x": 1}, Source.SEED),
        ({"x": 7}, Source.LLM_SEED),
    ]
    assert guesses.ran == [looped.records[1]]
    # the moment's own input does not start another moment
    assert len(guesses.moments) == 1


def test_five_inputs_in_a_row_with_no_new_line_make_a_run_stuck() -> None:
    summaries = Tool(Kind.SUMMARIES)
    limits = Limits(plateau=Plateau(inputs=10))

    go(loop_of(COUNTS, [summaries], limits), {"s": ""})

    # inputs 4 to 8 gain nothing, then the count starts again after the moment, and the plateau
    # stops the run after the second
    assert [(number, inputs) for number, inputs, _ in summaries.moments] == [(1, 8), (2, 13)]
    assert {entry.lines for _, _, entries in summaries.moments for entry in entries} == {(14,)}


def test_a_run_holds_at_most_three_moments_that_ask() -> None:
    summaries = Tool(Kind.SUMMARIES)

    go(loop_of(COUNTS, [summaries], Limits(plateau=Plateau(inputs=40))), {"s": ""})

    assert [(number, inputs) for number, inputs, _ in summaries.moments] == [
        (1, 8),
        (2, 13),
        (3, 18),
    ]


def test_a_wait_a_tool_pauses_for_moves_the_deadline() -> None:
    loop = loop_of(HANDLER, [Tool(Kind.GUESSES, pauses=60.0)], Limits())
    until = time.monotonic() + 3600
    loop.bounds = Bounds(until=until)

    go(loop, {"x": 1})

    assert loop.bounds.until == until + 60


def test_a_stop_a_tool_s_input_meets_ends_the_run() -> None:
    target = load_target(HANDLER)
    inputs = Inputs(target, Isolation.IN_PROCESS)
    calls: list[object] = []

    def second_refused(args: Mapping[str, object], until: float | None) -> ExecutionResult:
        calls.append(args)
        if len(calls) > 1:
            raise InputStartError("could not start a child process: refused")
        return inputs(args, until)

    guesses = Tool(Kind.GUESSES, runs={"x": 7})

    looped = go(loop_of(HANDLER, [guesses], call=second_refused), {"x": 1})

    assert guesses.ran == [
        Stop(StopKind.COULD_NOT_START, "could not start a child process: refused")
    ]
    assert looped.stop == guesses.ran[0]
    assert len(looped.records) == 1


def test_a_run_with_no_tool_is_never_stuck() -> None:
    looped = go(loop_of(HANDLER, []), {"x": 1})

    assert looped.stop == Stop(StopKind.NO_FORK)
    assert len(looped.records) == 1


def test_the_inputs_in_a_row_count_from_after_the_last_seed() -> None:
    summaries = Tool(Kind.SUMMARIES)
    loop = loop_of(COUNTS, [summaries], Limits(plateau=Plateau(inputs=10)))
    seeds = [{"s": ""}] * 6
    loop.bounds = Bounds.of(Limits(plateau=Plateau(inputs=10)), len(seeds))

    go(loop, *seeds)

    # five seeds in a row gain nothing, yet only the inputs after them count
    assert summaries.moments[0][1] >= len(seeds) + 5


def test_the_causes_part_way_count_an_open_fork_as_not_tried() -> None:
    loop = loop_of(IMPLIED, [])
    loop.run_input(Seed.of({"x": 3}), Source.SEED)

    causes = loop.causes(None)

    taken = {entry.lines: entry.tries for entry in causes if entry.reason is Reason.NOT_TAKEN}
    assert taken == {(5,): Tries(not_tried=1), (6,): Tries(not_tried=1)}
