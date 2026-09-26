"""A thread of the test's own beside the main one, so pyct's process runs more than one."""

import threading
from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def another_thread() -> Generator[None]:
    """A thread running beside the main one until the block ends.

    The system can hand it a SIGINT aimed at the whole process.
    """
    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
