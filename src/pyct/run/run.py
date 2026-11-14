"""Run one target with its seeds, then with an input per fork their inputs left open."""

from __future__ import annotations

import dataclasses
import platform
from collections.abc import Mapping, Sequence

from pyct.binding.bind import Seed
from pyct.config.limits import Limits
from pyct.results.coverage import Coverage, Scope
from pyct.results.record import Environment, RunResult, Source
from pyct.run.as_found import modules_as_found
from pyct.run.bounds import Bounds
from pyct.run.defaults import with_defaults
from pyct.run.helpers import Helpers
from pyct.run.isolation import Inputs
from pyct.run.llm_seeds import SeedProvider, ask_seeds
from pyct.run.loop import Loop, Start
from pyct.run.rewrites import Rewrites
from pyct.run.setup import Setup
from pyct.run.stuck import Stuck, StuckTool
from pyct.run.summaries import Summaries
from pyct.run.target import Target, argument_checks
from pyct.run.tell import Tell, Told
from pyct.run.token_limit import TokenLimit, heard_seeds
from pyct.solver import walk_keys
from pyct.solver.locate import locate, version

_NO_LIMITS = Limits()


def _platform() -> str:
    """The platform the summary line names, read with ``sys.modules`` left as it was found.

    The first read imports modules of its own, such as plistlib and datetime
    on macOS. Made here, as this module imports, it runs before a target's
    folder joins the import path, so none of them comes from that folder;
    ``modules_as_found`` then drops each one again, so a target that imports
    one gets it from its own path, as plain Python would. platform keeps
    what it read, so no later read imports them again. The read also runs
    one or two short commands, ``uname -p`` among them, about 10 ms in all.
    """
    with modules_as_found():
        return platform.platform()


_PLATFORM = _platform()

_TELL_NOTHING = Tell()

_PLAIN = Setup()


def run(
    target: Target,
    seed: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    limits: Limits = _NO_LIMITS,
    setup: Setup = _PLAIN,
    tell: Tell = _TELL_NOTHING,
) -> RunResult:
    """Call the target with each seed, then with an input per fork left open.

    ``seed`` is one seed, or several, which run in their order before any
    solver input, each adding its path to the one tree the solver works from.
    A run needs at least one, or ``setup.helpers.seeds``, which is asked once,
    before the first input, for seeds that run after these (``ask_seeds``),
    with the budget's clock paused while it answers. While a seed waits to run,
    the run does not stop on an empty tree, and the plateau counts only the
    inputs after the last seed; the budget and full coverage stop it as they
    would a solver input.

    ``setup.isolation`` says where each input runs: by default in a process
    of its own, and ``Isolation.IN_PROCESS`` runs every input in the
    caller's process (see ``Isolation``). Each input goes to
    ``tell.report`` as it finishes, with the coverage of that input alone, so
    an input that hangs never hides the lines of the ones before it. Each
    fork the solver could not flip goes to ``tell.missed`` the same way, so a
    reader sees it when its answer comes in, before the next input's trace.

    The run's coverage adds the lines the target's import ran
    (``Target.import_lines``) to the inputs'; the plateau reads the inputs'
    alone. Each seed's constructor arguments, under the ``self`` of a method
    whose instance each input builds, in each object it names with
    ``"__class__"``, and in each JSON object a class hint builds, first take
    the simple defaults it leaves out (``with_defaults``).
    """
    seeds = (seed,) if isinstance(seed, Mapping) else tuple(seed)
    if not seeds and setup.helpers.seeds is None:
        raise ValueError("a run needs at least one seed")
    scope = Scope.of_module(target.file)
    walk_keys.forget()
    inputs = Inputs(target, setup.isolation)
    # before the deadline starts: the probe is the run's setup, not its time
    cvc5 = version(locate())
    bounds = Bounds.of(limits, len(seeds))
    told = Told(scope=scope, tell=tell, imported=target.import_lines)
    limit = TokenLimit()
    starts, bounds = _starts(target, seeds, heard_seeds(setup.helpers.seeds, limit), bounds, told)
    summaries, rewrites = _tools(setup.helpers, target, told, limit)
    loop = _loop(inputs, bounds, told, summaries, rewrites)
    looped = loop.go(starts)
    covered = frozenset[int]().union(*(record.covered_lines for record in looped.records))
    return RunResult(
        entry=target.spec,
        records=looped.records,
        # the import's lines count once, for the run, and in no input's coverage
        coverage=Coverage.of(scope, covered | target.import_lines),
        stopped=looped.stop,
        environment=_environment(cvc5, inputs.isolated),
        misses=looped.misses,
        untried=looped.untried,
        # the loop's own, which each wait for the LLM moved later
        deadline=loop.bounds.until,
        goal=limits.goal,
        summaries=() if summaries is None else summaries.states(),
    )


def _tools(
    helpers: Helpers, target: Target, told: Told, limit: TokenLimit
) -> tuple[Summaries | None, Rewrites | None]:
    """The LLM tools that take missed lines, each that is switched on, sharing the run's token
    limit."""
    summaries = helpers.summaries
    rewrites = helpers.rewrites
    return (
        None if summaries is None else Summaries(summaries, target, told, limit),
        None if rewrites is None else Rewrites(rewrites, target, told, limit),
    )


def _loop(
    inputs: Inputs,
    bounds: Bounds,
    told: Told,
    summaries: Summaries | None,
    rewrites: Rewrites | None,
) -> Loop:
    """The run's loop, with each LLM tool that takes missed lines switched on in its moments:
    none, and the run is never stuck."""
    tools: list[StuckTool] = [tool for tool in (summaries, rewrites) if tool is not None]
    if not tools:
        return Loop(inputs, bounds, told)
    return Loop(inputs, bounds, told, Stuck(tools), rewrites)


def _starts(
    target: Target,
    seeds: Sequence[Mapping[str, object]],
    provider: SeedProvider | None,
    bounds: Bounds,
    told: Told,
) -> tuple[tuple[Start, ...], Bounds]:
    """Each seed copied, the user's then the LLM's, and the bounds with the LLM's wait paused
    and its seeds counted. With no seeds helper, the user's seeds alone.

    The ask comes once the deadline is set and before the first input. Its wait is added back
    to the budget; building the request and checking the seeds count toward it.
    """
    asked = None if provider is None else ask_seeds(provider, target, seeds, bounds.goal, told)
    checks = argument_checks(target)
    starts = [Start(Seed.of(with_defaults(target, each), checks, target.home)) for each in seeds]
    if asked is None:
        return tuple(starts), bounds
    for each in asked.seeds:
        copy = Seed.of(with_defaults(target, each), checks, target.home)
        starts.append(Start(copy, Source.LLM_SEED))
    counted = dataclasses.replace(bounds, seeds=len(starts))
    return tuple(starts), counted.paused(asked.waited)


def _environment(cvc5: str | None, isolated: bool) -> Environment:
    """What the run ran in: the version the solver's cvc5 reported, and where inputs ran.

    A cvc5 that will not say its version leaves the version out; the run is
    the same run either way. ``isolated`` is known only once the inputs ran,
    since a run can move to pyct's own process part way.
    """
    return Environment(
        python=platform.python_version(),
        cvc5=cvc5,
        platform=_PLATFORM,
        isolated=isolated,
    )
