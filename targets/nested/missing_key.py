def check(config):
    port = config["server"]["port"]
    if port < 1:
        return "low"
    return "ok"
