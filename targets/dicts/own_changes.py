def check(config):
    config["seen"] = 1
    for v in config.values():
        if v > 5:
            return "big"
    return "small"
