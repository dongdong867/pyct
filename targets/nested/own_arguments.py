def touch(items, config):
    # an earlier input's changes would still be here: the None it appended, or the key it set
    if (items and items[-1] is None) or config:
        raise ValueError("an earlier input changed the arguments")
    items.append(None)
    config["seen"] = True
    if items[0] is not None and items[0] > 5:
        return "big"
    return "small"
