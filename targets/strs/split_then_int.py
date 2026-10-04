def content_range(value):
    try:
        units, rangedef = value.strip().split(None, 1)
    except ValueError:
        return "no units"
    if "/" not in rangedef:
        return "no length"
    rng, length_str = rangedef.split("/", 1)
    if length_str == "*":
        length = None
    else:
        try:
            length = int(length_str.strip())
        except ValueError:
            return "bad length"
    if rng == "*":
        if length is not None and length < 0:
            return "negative length"
        return "any range"
    return "a range"
