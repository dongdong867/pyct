def touch(items, config):
    if len(items) != 1 or config:
        raise ValueError("an earlier input changed the arguments")
    items.append(99)
    config["seen"] = True
    if items[0] > 5:
        return "big"
    return "small"
