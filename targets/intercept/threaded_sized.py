import threading
import time


def _keep_running() -> None:
    while True:
        time.sleep(1)


# a thread the import starts and never stops, so each input runs in a fresh interpreter
threading.Thread(target=_keep_running, name="left running", daemon=True).start()


def check(s: str) -> str:
    if len(s) > 3:
        return "long"
    return "short"
