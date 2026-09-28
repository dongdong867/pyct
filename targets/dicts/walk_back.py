def check(config: dict[str, int]):
    for key in reversed(config):
        if config[key] > 5:
            return key
    return None
