def check(config):
    node = config
    while isinstance(node, dict):
        node = node["a"]
    if node > 5:
        return "big"
    return "small"
