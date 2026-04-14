"""Target that branches on empty-string equality."""


def is_empty(s: str) -> bool:
    if s == "":  # noqa: SIM103 — explicit branch required for concolic tracking
        return True
    return False
