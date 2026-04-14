"""Integer range target — conjunction of comparison branches (4 distinct categories)."""


def categorize_value(x: int) -> str:
    if x < 0:
        return "negative"
    if x < 10:
        return "small"
    if x < 100:
        return "medium"
    return "large"
