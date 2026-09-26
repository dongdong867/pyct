def check(config):
    server = config["server"]
    if server["port"] < 1:
        return "low"
    if server["port"] > 65535:
        return "high"
    if server["host"] == "localhost":
        return "local"
    return "ok"
