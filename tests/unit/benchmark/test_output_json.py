"""``save_results_json`` falls back to ``repr`` for non-serializable values.

Records harvested from the engine may carry args whose values are not
JSON-serializable (frozensets, ``object()`` instances, lambdas that
slipped past the parser sanitizer). The benchmark JSON writer must keep
working — failing the whole results dump to surface one bad arg would
hide every other measurement in the run. ``json.dumps(default=repr)``
gives a readable fallback for the bad value while every other field
serializes normally.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.output import save_results_json


def _payload_with_unserializable_arg() -> list[dict]:
    """Construct an all_results entry with an unjsonable arg value."""
    sentinel = object()
    return [
        {
            "target": "x",
            "runner_results": {
                "llm_only": {
                    "success": True,
                    "input_records": [
                        {
                            "args": {"x": sentinel},
                            "provenance": "plugin_seed",
                            "outcome": "covered_new",
                            "new_lines": [1, 2],
                            "error": None,
                        }
                    ],
                    "gen_unsat": 0,
                    "gen_unknown": 0,
                    "gen_parse_failed": 0,
                    "harness_error": 0,
                }
            },
        }
    ]


def test_save_results_json_does_not_raise_on_unserializable_arg(tmp_path: Path) -> None:
    out = tmp_path / "results.json"
    config = BenchmarkConfig()

    # No raise on unserializable values — repr fallback keeps the dump alive.
    save_results_json(_payload_with_unserializable_arg(), config, out)

    text = out.read_text()
    payload = json.loads(text)

    record = payload["results"][0]["runner_results"]["llm_only"]["input_records"][0]
    # The bad arg is stringified via repr (object() -> "<object object at 0x...>").
    assert isinstance(record["args"]["x"], str)
    assert record["args"]["x"].startswith("<object")


def test_save_results_json_preserves_native_types(tmp_path: Path) -> None:
    """Normal records keep their types — int / bool / list pass through."""
    out = tmp_path / "results.json"
    config = BenchmarkConfig()
    payload = [
        {
            "target": "x",
            "runner_results": {
                "llm_only": {
                    "success": True,
                    "input_records": [
                        {
                            "args": {"i": 7, "b": True, "lst": [1, 2, 3]},
                            "provenance": "plugin_seed",
                            "outcome": "no_gain",
                            "new_lines": [],
                            "error": None,
                        }
                    ],
                }
            },
        }
    ]

    save_results_json(payload, config, out)

    record = json.loads(out.read_text())["results"][0]["runner_results"]["llm_only"][
        "input_records"
    ][0]
    assert record["args"] == {"i": 7, "b": True, "lst": [1, 2, 3]}
    assert record["new_lines"] == []
