def check(items, config, note):
    if len(items) > 3:
        return "long"
    if "port" in config:
        return "configured"
    if note is not None:
        return "noted"
    if items[0] > 0:
        return "positive"
    return "other"
