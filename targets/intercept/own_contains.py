class Box:
    def __contains__(self, item: object) -> bool:
        return 1 // 0 == item


def look(x: int) -> str:
    box = Box()
    if x in box:
        return "in"
    return "not in"
