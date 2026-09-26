import os
import signal


def stop(x: int) -> str:
    if x > 3:
        # ends this process by a signal, one whose default action writes no crash report
        os.kill(os.getpid(), signal.SIGTERM)
    return "kept going"
