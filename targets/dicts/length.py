def check(config):
    config["n"] = 1
    if len(config) > 2:
        return "big"
    return "small"
