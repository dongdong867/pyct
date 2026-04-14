"""Empty-dict target — membership check on a constant empty dict."""


def always_absent(key: str) -> bool:
    empty: dict[str, int] = {}
    if key in empty:  # noqa: SIM103 — explicit branch required for concolic tracking
        return True
    return False
