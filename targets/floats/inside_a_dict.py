def check(config):
    if config["ratio"] > 0.5:
        return "high"
    if config["count"] > 3:
        return "many"
    return "low"
