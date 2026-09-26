class Halt(BaseException):
    """A raise of the target's own that is neither an Exception nor SystemExit."""


def stop(x: int, y: int) -> str:
    if x > 3:
        raise KeyboardInterrupt
    if y > 3:
        raise Halt("halted")
    return "went on"
