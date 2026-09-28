def check(items, config):
    items.append(1)
    config["n"] = 2
    if items[0] > 5:
        return "item"
    if config["a"] > 5:
        return "value"
    return "none"
