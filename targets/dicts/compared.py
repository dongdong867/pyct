def check(config: dict[str, str]):
    if config == {"mode": "fast"}:
        return "fast"
    return "other"
