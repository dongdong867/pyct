"""The mark for a test whose deadline fires in the test process: it runs with coverage paused.

coverage.py's tracer calls back into Python to lock its data. The deadline raises from a
SIGALRM handler, and Python can run that handler inside the callback, after the lock is taken
or before it is released. The lock then stays held, and the next traced call waits on it
forever. With coverage paused for the test, the tracer takes no lock. The lines these tests
reach are still measured in the pyct subprocesses the acceptance tests run with a budget.
"""

import pytest

DEADLINE_FIRES = pytest.mark.no_cover
