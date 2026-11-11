"""The worker prints one JSON line for every ask, its adapter's failures included."""

import dataclasses
import io
import json

import pytest

from pyct.llm import worker


def test_an_adapter_that_cannot_import_is_the_error_s_class(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = dataclasses.replace(worker.PROVIDERS["openai"], adapter="pyct.llm.no_such_adapter")
    request = {"provider": "openai", "model": "m", "text": "the request", "out_tokens": 10}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    monkeypatch.setitem(worker.PROVIDERS, "openai", missing)

    assert worker.main() == 0
    assert json.loads(capsys.readouterr().out) == {"error": "ModuleNotFoundError", "status": None}
