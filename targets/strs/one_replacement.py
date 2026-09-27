def swap(s: str) -> str:
    if s.replace("a", "b", 1) == "bab":
        return "swapped"
    return "other"
