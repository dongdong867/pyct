def is_flag(value: object) -> bool:
    return isinstance(value, bool)


def class_of(value: object) -> object:
    return value.__class__


def rebuild(value: object, made_from: object) -> object:
    return type(value)(made_from)
