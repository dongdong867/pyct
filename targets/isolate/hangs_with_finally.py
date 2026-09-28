import sys

# what the finally block writes once the hang is ended
MARKER = "the hang's finally block ran"


def hang(x: int) -> str:
    try:
        while True:
            pass
    finally:
        print(MARKER, file=sys.stderr, flush=True)
