def grade(x: int) -> str:
    if x < 10:
        return "small"
    label = "large"
    label += "!"
    return label
