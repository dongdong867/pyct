"""The pyct command line.

``pyct run MODULE::FUNCTION [JSON] [--args JSON] [--seeds FILE] [--budget SECONDS]
[--plateau N] [--solver-timeout SECONDS] [--in-process] [--goal coverage|bugs]
[--dump-formulas DIR] [--llm TOOLS] [--llm-model PROVIDER:MODEL]``

``pyct sweep PACKAGE [--list] [--budget SECONDS] [--plateau N] [--solver-timeout SECONDS]
[--total-budget SECONDS] [--goal coverage|bugs]``
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.binding.bind import access_name, leaves
from pyct.cli.llm import add_flags as add_llm_flags
from pyct.cli.shared import Parser, line
from pyct.cli.sweep import (
    SWEEP_USAGE,
    SweepCommand,
    run_sweep,
    sweep_command,
    sweep_parser,
)
from pyct.config.budget import RUN_SECONDS
from pyct.config.command_line import (
    NO_DEADLINE,
    UsageError,
    dump_folder,
    parse_budget,
    parse_goal,
    parse_plateau,
    parse_solver_timeout,
)
from pyct.config.limits import Limits
from pyct.config.llm import parse_llm
from pyct.execution.deadline import own_the_alarm
from pyct.intercept.cache import CACHE_HELP
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render, render_summary
from pyct.results.printed import printed_forks
from pyct.results.record import InputRecord, Miss, RunResult, Source, StopKind
from pyct.results.trace import render_miss, render_start, render_stop, render_trace
from pyct.run.import_watch import ImportWatch
from pyct.run.isolation import Isolation
from pyct.run.launch import launch
from pyct.run.run import run
from pyct.run.seed_checks import check_seed, missing_args_message, parse_seed
from pyct.run.seeds_file import SeedsFile, checked_seeds, distinct, read_seeds_file
from pyct.run.setup import Setup
from pyct.run.target import Target, TargetError, interception, load_target
from pyct.run.tell import Ask, Tell
from pyct.solver.given import write
from pyct.solver.locate import SolverMissingError, locate
from pyct.sweep.listing import PackageImportError

USAGE = (
    "pyct run MODULE::FUNCTION [JSON] [--args JSON] [--seeds FILE] [--budget SECONDS]"
    " [--plateau N] [--solver-timeout SECONDS] [--in-process] [--goal coverage|bugs]"
    " [--dump-formulas DIR] [--llm TOOLS] [--llm-model PROVIDER:MODEL]"
)
# the refusal of seeds given more than one way
ONE_WAY = "give the seeds one way: after the target, through --args, or through --seeds"


@dataclass(frozen=True)
class RunCommand:
    """What the command line asked for: the target spec, the seed, the three limits, and where.

    ``seeds_text`` names a file of seeds, given instead of ``seed_text``.
    ``in_process`` runs every input in pyct's own process rather than one of its own.
    ``goal_text`` is the goal as written, None for the default, and ``dump_text`` the folder
    each program pyct gives cvc5 goes to, None for none. ``llm_text`` and ``llm_model_text`` are
    ``--llm`` and ``--llm-model`` as written, None when not given.
    """

    spec: str
    seed_text: str | None
    budget_text: str | None = None
    plateau_text: str | None = None
    solver_timeout_text: str | None = None
    in_process: bool = False
    goal_text: str | None = None
    dump_text: str | None = None
    seeds_text: str | None = None
    llm_text: str | None = None
    llm_model_text: str | None = None


@dataclass(frozen=True)
class Seeds:
    """The seeds a run starts from, in order; each one's ``FILE:N`` when a seeds file gave them;
    and a ``skipped`` line for each line of the file that repeated an earlier seed."""

    seeds: tuple[Mapping[str, object], ...]
    labels: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def entry() -> int:
    """The command line as the shell starts it: ``main`` in a process of its own, watched here.

    A target whose import ends its process, by ``os._exit`` or a signal,
    ends the process ``main`` runs in, so the process the shell started
    outlives it to say so (see ``pyct.run.launch``). Tests call ``main`` in
    their own process instead.
    """
    # pyct owns the processes the shell starts, so its deadline takes SIGALRM for good
    own_the_alarm()
    argv = sys.argv[1:]
    return launch(functools.partial(main, argv), argv)


def main(argv: Sequence[str] | None = None, watch: ImportWatch | None = None) -> int:
    """Run the command line and return the exit code.

    0: the lines were printed. 1: cvc5 is missing or crashed, the target
    could not be loaded, pyct could not start a process for an input, or
    pyct itself broke during the run. 2: usage.

    The run prints each input as it finishes, through ``_report``, and each
    fork the solver could not flip, through ``_missed``, so a second input
    that hangs never hides the first one's line. Why the run stopped is a
    fact about the whole run, so it ends stderr, and the summary line ends
    stdout after it: the readable text comes first, as it does for every
    input. A class target first says, once, that each input constructs it.

    The target's package is substituted from its import to the run's end,
    in this process and in every input's (``pyct.intercept``).

    Checks run in this order: target form, seed shape or the seeds file's
    read, budget, plateau, solver timeout, goal, dump folder, the LLM flags, import and
    signature, seed present, seed fits, seed types, cvc5. A seeds file's
    lines take the shape, fit and type checks in one pass after the import,
    so every bad line is named at once. A line that repeats an earlier seed is said once
    the checks pass, before the first input.
    Everything the command line got wrong is reported first, because a wrong
    command line is wrong whatever the machine has installed; cvc5 is the
    last check before the run for the same reason, as it is the only one
    about the machine. The import comes before the three seed checks because
    they all read the loaded target: its parameters, and the annotations on
    them.

    While the target imports, ``watch`` names its module for the process
    that watches this one, when ``entry`` started one.
    """
    try:
        command = parse_command(sys.argv[1:] if argv is None else argv)
        if isinstance(command, SweepCommand):
            return run_sweep(command)
        with interception(command.spec):
            target, seeds, limits, tell = _checked(command, watch)
            print(render_start(command.spec, target.fn), end="", file=sys.stderr, flush=True)
            for skipped in seeds.skipped:
                print(skipped, file=sys.stderr, flush=True)
            result = run(
                target,
                seeds.seeds,
                limits=limits,
                setup=Setup(
                    isolation=Isolation.IN_PROCESS if command.in_process else Isolation.AUTO
                ),
                tell=tell,
            )
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (SolverMissingError, TargetError, PackageImportError) as error:
        print(error, file=sys.stderr)
        return 1
    print(render_stop(result), end="", file=sys.stderr, flush=True)
    line(render_summary(result))
    return _exit_code(result)


def _checked(command: RunCommand, watch: ImportWatch | None) -> tuple[Target, Seeds, Limits, Tell]:
    """Every check before the run, in the order ``main`` gives. Each raises what main reports.

    The Tell prints each input and miss, and writes each ask's programs to the dump folder when
    the command line names one."""
    check_spec(command.spec)
    seed = None if command.seed_text is None else parse_seed(command.seed_text)
    file = None if command.seeds_text is None else read_seeds_file(command.seeds_text)
    limits = Limits(
        budget=parse_budget(command.budget_text, RUN_SECONDS),
        plateau=parse_plateau(command.plateau_text),
        solver_timeout=parse_solver_timeout(command.solver_timeout_text),
        goal=parse_goal(command.goal_text),
    )
    folder = dump_folder(command.dump_text)
    parse_llm(command.llm_text, command.llm_model_text)
    asked = None if folder is None else _Dump(folder).ask
    target = load_target(command.spec, watch)
    seeds = _seeds(target, seed, file)
    locate()
    report = _Labeled(seeds.labels).report
    return target, seeds, limits, Tell(report=report, missed=_missed, asked=asked)


def _seeds(target: Target, seed: Mapping[str, object] | None, file: SeedsFile | None) -> Seeds:
    """The seed checked, or every line of the seeds file checked and its repeats left out."""
    if file is not None:
        kept, skipped = distinct(checked_seeds(target, file))
        return Seeds(tuple(each.seed for each in kept), tuple(each.label for each in kept), skipped)
    if seed is None:
        raise UsageError(missing_args_message(target.signature))
    check_seed(target, seed)
    return Seeds((seed,))


class _Labeled:
    """Hands each seed's ``FILE:N`` to its trace, in the order the seeds run."""

    def __init__(self, labels: Sequence[str]) -> None:
        self.waiting = iter(labels)

    def report(self, record: InputRecord, coverage: Coverage) -> None:
        # a seed given inline has no label
        label = next(self.waiting, None) if record.source is Source.SEED else None
        _report(record, coverage, label)


class _Dump:
    """Writes each ask's programs into the dump folder, each headed by its aim and its input.

    A write that fails, a folder made unwritable or a full disk, is said once on stderr and
    ends the dump; the run goes on."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.writing = True

    def ask(self, ask: Ask) -> None:
        if not self.writing:
            return
        site = ask.aim.site
        about = (
            f"aim {site.file}:{site.line}:{site.col} at position {ask.aim.position},"
            f" on the path of stdout line {ask.path + 1}"
        )
        try:
            write(self.folder, ask.number, about, ask.programs)
        except OSError as error:
            self.writing = False
            print(
                f"cannot write {error.filename}: {error.strerror}; writing no more asks",
                file=sys.stderr,
                flush=True,
            )


def _report(record: InputRecord, coverage: Coverage, label: str | None = None) -> None:
    """The trace a person reads first, then the one line tools read. ``label`` names where a
    seed came from in its trace.

    Both print each fork's expression cut to the cap, and it is cut once for both.
    An access to one of the input's values is a name, written whole. A seed with
    no value inside an argument has no access to name, and no part is asked.
    """
    names = leaves(record.args)
    if names.keys() <= record.args.keys():
        printed = printed_forks(record.forks)
    else:
        # each part's access, once: a path through a deep dict names every step of its chain
        known: dict[int, str | None] = {}
        printed = printed_forks(record.forks, lambda part: access_name(part, known) in names)
    print(render_trace(record, coverage, printed, label), end="", file=sys.stderr, flush=True)
    line(render(record, coverage, printed))


def _missed(miss: Miss) -> None:
    """The fork the solver gave no input for, printed where its answer came in."""
    print(render_miss(miss), end="", file=sys.stderr, flush=True)


def _exit_code(result: RunResult) -> int:
    """Every line is printed either way; a dead solver, an input that could not start, or a
    pyct bug still ends it badly."""
    if result.stopped.kind in (StopKind.SOLVER_FAILED, StopKind.COULD_NOT_START):
        return 1
    return 1 if any(_is_a_bug(record.failure) for record in result.records) else 0


def _is_a_bug(failure: Failure | None) -> bool:
    return failure is not None and failure.kind is FailureKind.PYCT_BUG


def parse_command(argv: Sequence[str]) -> RunCommand | SweepCommand:
    """Read the argv. The seed may follow the target, or come through ``--args``, or a file of
    seeds through ``--seeds``: one of the three."""
    parser = Parser(prog="pyct", usage=f"{USAGE}\n       {SWEEP_USAGE}")
    commands = parser.add_subparsers(dest="command", required=True)
    sweep_parser(commands)
    _run_parser(commands)
    namespace = parser.parse_args(argv)
    if namespace.command == "sweep":
        return sweep_command(namespace)
    return _run_command(namespace)


def _run_parser(commands: argparse._SubParsersAction[Parser]) -> None:
    """The ``run`` command."""
    run_parser = commands.add_parser("run", usage=USAGE, epilog=CACHE_HELP)
    run_parser.add_argument("target", metavar="MODULE::FUNCTION")
    run_parser.add_argument("seed", nargs="?", metavar="JSON")
    run_parser.add_argument("--args", dest="args_seed", metavar="JSON")
    run_parser.add_argument("--seeds", dest="seeds_file", metavar="FILE")
    run_parser.add_argument(
        "--budget",
        metavar="SECONDS",
        help=f"the run's seconds; {RUN_SECONDS:g} by default, {NO_DEADLINE} for no deadline",
    )
    run_parser.add_argument("--plateau", metavar="N")
    run_parser.add_argument("--solver-timeout", metavar="SECONDS")
    run_parser.add_argument("--in-process", action="store_true")
    run_parser.add_argument("--goal", metavar="coverage|bugs")
    run_parser.add_argument("--dump-formulas", dest="dump", metavar="DIR")
    add_llm_flags(run_parser)


def _run_command(namespace: argparse.Namespace) -> RunCommand:
    """The run the argv asked for, refused when it gives its seeds more than one way."""
    inline = namespace.seed is not None or namespace.args_seed is not None
    if namespace.seed is not None and namespace.args_seed is not None:
        raise UsageError(f"give the seed once, after the target or through --args\nusage: {USAGE}")
    if namespace.seeds_file is not None and inline:
        raise UsageError(f"{ONE_WAY}\nusage: {USAGE}")
    seed_text = namespace.seed if namespace.seed is not None else namespace.args_seed
    return RunCommand(
        spec=namespace.target,
        seed_text=seed_text,
        budget_text=namespace.budget,
        plateau_text=namespace.plateau,
        solver_timeout_text=namespace.solver_timeout,
        in_process=namespace.in_process,
        goal_text=namespace.goal,
        dump_text=namespace.dump,
        seeds_text=namespace.seeds_file,
        llm_text=namespace.llm,
        llm_model_text=namespace.llm_model,
    )


def check_spec(spec: str) -> None:
    """Refuse anything but ``module::name``, each part a name; a name may be names joined by
    dots, as ``Cart.total``. A path is not a module."""
    module, separator, name = spec.partition("::")
    parts = [*module.split("."), *name.split(".")]
    named = bool(separator) and all(part.isidentifier() for part in parts)
    # `mod.py` is every part a name, and still a file path rather than a module
    if not named or module.endswith(".py"):
        raise UsageError(f"target must be MODULE::FUNCTION, got {spec!r}")
