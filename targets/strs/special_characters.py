def match(s: str) -> str:
    if s == "a\nb\"c\\d é":
        return "exact"
    return "other"
