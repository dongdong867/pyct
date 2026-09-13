def narrow(x: int) -> str:
    if x < 5:
        if x < 10:
            return "small"
        return "impossible"
    return "large"
