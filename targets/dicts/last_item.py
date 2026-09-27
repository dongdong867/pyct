def check(config):
    key, value = config.popitem()
    if value > 5:
        if "a" in config:
            return 2
        return 1
    return 0
