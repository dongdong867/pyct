import threading
import time
from collections.abc import Callable


def _keep_running() -> None:
    while True:
        time.sleep(1)


# a thread the import starts and never stops
threading.Thread(target=_keep_running, name="left running", daemon=True).start()


def make() -> Callable[[int], str]:
    """A counter no module attribute names: it lives in the closure make returns."""
    calls = 0

    def count(x: int) -> str:
        nonlocal calls
        calls += 1
        if x > 3:
            return f"big {calls}"
        return f"small {calls}"

    return count
