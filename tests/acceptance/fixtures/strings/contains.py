"""String contains target — substring-search constraint."""


def has_protocol(url: str) -> bool:
    if "://" in url:
        return True
    return False
