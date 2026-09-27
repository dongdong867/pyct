def classify(h: int, w: int) -> str:
    bmi = w / ((h / 100) * (h / 100))
    if bmi >= 25.0:
        return "over"
    return "under"
