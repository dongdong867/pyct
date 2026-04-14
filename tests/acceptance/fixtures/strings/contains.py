"""String contains target — substring-search constraint."""


def has_protocol(url: str) -> bool:
    return "://" in url
