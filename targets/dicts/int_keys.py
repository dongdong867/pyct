def annotated(config: dict[int, str]):
    if 3 in config:
        if config[3] == "x":
            return "x"
        return "other"
    return "none"


def unannotated(config):
    if 3 in config:
        return "three"
    return "none"
