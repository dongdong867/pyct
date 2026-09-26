import threading
import time

CALLS = 0


def _keep_running() -> None:
    while True:
        time.sleep(1)


# a thread the import starts and never stops
threading.Thread(target=_keep_running, name="left running", daemon=True).start()


def count(x: int) -> str:
    global CALLS
    CALLS += 1
    seen = False
    if CALLS > 1:
        seen = True  # marked: runs only when an earlier call left the count above 0
    if x > 3:
        return f"big {seen}"
    return f"small {seen}"
