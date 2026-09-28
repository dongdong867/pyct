"""A test marked ``no_cover`` runs with no coverage.py tracer, in any thread it starts.

Under xdist a worker also runs the measurement coverage.py's subprocess patch
started in it, which pytest-cov does not stop; ``tests/conftest.py`` stops it.
Without ``--cov`` there is no tracer to begin with.
"""

import sys
import threading

from tests.unit.deadline_fires import DEADLINE_FIRES


@DEADLINE_FIRES
def test_a_test_whose_deadline_fires_runs_with_no_tracer() -> None:
    seen: list[object] = []
    thread = threading.Thread(target=lambda: seen.append(sys.gettrace()))
    thread.start()
    thread.join()

    assert sys.gettrace() is None
    assert seen == [None]
