"""The adapter in this process with a fake engine: the config it builds, the line it prints."""

import json
import os
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools.compare_coverage import legacy_adapter
from tools.compare_coverage.legacy_adapter import Engine, main, report


@dataclass(frozen=True)
class Record:
    error: str | None


@dataclass(frozen=True)
class Answer:
    success: bool = True
    executed_lines: frozenset[int] = frozenset({2, 3})
    iterations: int = 4
    termination_reason: str = "exhausted"
    error: str | None = None
    inputs_generated: tuple[Record, ...] = ()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A root holding one target module; the path and module edits are undone after the test."""
    (tmp_path / "adapter_target.py").write_text("def f(x):\n    return x\n")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "adapter_target", raising=False)
    return tmp_path


def fake_engine(answer: Answer, calls: list[dict[str, Any]]) -> Engine:
    def run_concolic(target: Any, seed: dict[str, Any], **options: Any) -> Answer:
        calls.append({"target": target, "seed": seed, **options})
        print("engine talks on stdout")
        os.write(1, b"so does the target\n")
        return answer

    scope = SimpleNamespace(for_paths=lambda paths: ("scope", tuple(paths)))
    return Engine(run_concolic=run_concolic, config=dict, scope=scope)


def a_request(root: Path, target: str = "adapter_target::f") -> dict[str, Any]:
    limits = {"budget": 5.0, "plateau": 3, "solver_timeout": 3}
    return {"target": target, "seed": {"x": 1}, "root": str(root), "limits": limits}


def test_the_config_lifts_the_input_cap_and_bounds_the_seed_by_the_budget(root: Path) -> None:
    calls: list[dict[str, Any]] = []

    report(a_request(root), fake_engine(Answer(), calls))

    (call,) = calls
    file = str(root / "adapter_target.py")
    assert call["config"] == {
        "timeout_seconds": 5.0,
        "seed_soft_timeout": 5.0,
        "max_iterations": sys.maxsize,
        "plateau_threshold": 3,
        "solver_timeout": 3,
        "scope": ("scope", (file,)),
    }
    assert call["seed"] == {"x": 1}
    assert call["plugins"] is None
    assert call["target"].__module__ == "adapter_target"


def test_the_line_holds_the_file_lines_stop_and_inputs(root: Path) -> None:
    line = report(a_request(root), fake_engine(Answer(), []))

    assert line == {
        "file": str(root / "adapter_target.py"),
        "covered": [2, 3],
        "stopped": "exhausted",
        "inputs": 4,
        "failure": None,
    }


def test_an_engine_that_says_it_failed_is_a_failure_with_its_text(root: Path) -> None:
    answer = Answer(success=False, termination_reason="error", error="cannot inspect target")

    line = report(a_request(root), fake_engine(answer, []))

    assert line["failure"] == "error: cannot inspect target"


def test_a_failure_without_text_names_the_last_inputs_error(root: Path) -> None:
    # legacy's watchdog returns its last checkpoint with no error, and the stopped input last
    inputs = (Record(error=None), Record(error="timeout: child exceeded wall-clock timeout"))
    answer = Answer(success=False, termination_reason="timeout", inputs_generated=inputs)

    line = report(a_request(root), fake_engine(answer, []))

    assert line["failure"] == "timeout: timeout: child exceeded wall-clock timeout"


def test_a_failure_with_no_text_anywhere_says_the_result_is_partial(root: Path) -> None:
    answer = Answer(success=False, termination_reason="partial_checkpoint")

    line = report(a_request(root), fake_engine(answer, []))

    assert line["failure"] == "partial_checkpoint: legacy gave a partial result and no error"


def test_a_target_that_does_not_import_is_a_failure(root: Path) -> None:
    line = report(a_request(root, "adapter_target::g"), fake_engine(Answer(), []))

    assert line["file"] is None
    assert line["failure"].startswith("cannot import adapter_target::g: AttributeError(")


def test_a_module_with_no_file_is_a_failure(root: Path) -> None:
    (root / "namespace_only").mkdir()

    line = report(a_request(root, "namespace_only::f"), fake_engine(Answer(), []))

    assert "namespace_only has no source file" in line["failure"]


def test_main_prints_only_the_line_on_stdout(root: Path, capfd: pytest.CaptureFixture[str]) -> None:
    argv = ["legacy_adapter.py", json.dumps(a_request(root))]

    assert main(argv, lambda: fake_engine(Answer(), [])) == 0

    out, err = capfd.readouterr()
    assert [json.loads(line)["inputs"] for line in out.splitlines()] == [4]
    assert "engine talks on stdout" in err
    assert "so does the target" in err


def fake_legacy(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    """Modules named as legacy's are, holding the fake engine, where an import finds them first."""
    engine = fake_engine(Answer(), calls)
    package = SimpleNamespace(run_concolic=engine.run_concolic, ExecutionConfig=engine.config)
    monkeypatch.setitem(sys.modules, "pyct", package)
    monkeypatch.setitem(
        sys.modules, "pyct.engine.coverage_scope", SimpleNamespace(CoverageScope=engine.scope)
    )


def test_the_engine_is_taken_by_name_from_legacys_modules(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    fake_legacy(monkeypatch, calls)

    engine = legacy_adapter.load_engine()
    report(a_request(root), engine)

    assert len(calls) == 1
    assert engine.config is dict


def test_run_as_a_script_it_exits_after_the_one_line(
    root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    fake_legacy(monkeypatch, [])
    monkeypatch.setattr(sys, "argv", ["legacy_adapter.py", json.dumps(a_request(root))])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(legacy_adapter.__file__, run_name="__main__")

    assert exited.value.code == 0
    out, _ = capfd.readouterr()
    assert json.loads(out)["file"] == str(root / "adapter_target.py")
