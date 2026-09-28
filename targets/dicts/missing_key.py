def check(config: dict[str, dict[str, int]]):
    port = config["server"]["port"]
    if port < 1:
        return "low"
    return "ok"
