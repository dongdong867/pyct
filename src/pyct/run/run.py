"""Run one target once with one seed."""

from collections.abc import Mapping

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.coverage import Coverage, Scope
from pyct.results.record import InputRecord, RunResult
from pyct.run.target import Target


def run(target: Target, seed: Mapping[str, object]) -> RunResult:
    """Call the target with the seed as keyword arguments and measure it against its module."""
    scope = Scope.of_module(target.file)
    ctx = ExecutionContext(fn=target.fn, file=target.file)
    executed = execute(ctx, seed)
    coverage = Coverage.of(scope, executed.lines)
    record = InputRecord(
        args=seed, forks=executed.branches, covered_lines=coverage.covered[scope.file]
    )
    return RunResult(entry=target.spec, records=(record,), coverage=coverage)
