def check(config: dict[str, int]):
    if config:
        for name, limit in config.items():
            if limit > 10:
                return name
        return "some"
    return "none"
