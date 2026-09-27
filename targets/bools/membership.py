def member(x: int, y: int) -> str:
    if x in (1, 2, 3):
        return "small"
    if y not in [4, 5]:
        return "not four or five"
    return "four or five"
