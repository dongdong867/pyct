def get_float(d):
    if d.get("k", 0.0) > 2.5:
        return "above"
    return "other"


def get_bool(d):
    if d.get("k", False):
        return "on"
    return "off"


def walk_items(d):
    for key, value in d.items():
        if value > 1.5:
            return key
    return "none"


def walk_values(d):
    for value in d.values():
        if value:
            return "on"
    return "off"


def under_tracked_key(table, name):
    if name in table:
        if table[name] > 2.5:
            return "above"
    return "other"


def annotated_float(d: dict[str, float]):
    if "k" in d:
        if d["k"] > 2.5:
            return "above"
    return "other"


def annotated_bool(d: dict[str, bool]):
    if d.get("k"):
        return "on"
    return "off"
