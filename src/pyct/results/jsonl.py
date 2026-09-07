"""The one JSON line per input that other tools read from stdout."""

import json

from pyct.results.coverage import Coverage
from pyct.results.record import InputRecord


def render(record: InputRecord, coverage: Coverage) -> str:
    """One line, no newline inside; line numbers sorted so the text is stable."""
    payload = {
        "args": record.args,
        "covered": {file: sorted(lines) for file, lines in coverage.covered.items()},
        "total": dict(coverage.total),
    }
    return json.dumps(payload)
