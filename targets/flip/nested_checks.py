def bucket(x: int) -> str:
    if x < 100:
        if x < 10:
            return "small"
        return "medium"
    return "large"
