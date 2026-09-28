def check(name, prices):
    if name in prices:
        if prices[name] > 5:
            return "dear"
        return "cheap"
    return "missing"
