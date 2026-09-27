"""A sweep fixture: a private module whose function the package re-exports."""


def parse_price(text: str) -> int:
    if text == "free":
        return 0
    return len(text)
