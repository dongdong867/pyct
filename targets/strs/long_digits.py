def card(number: str) -> str:
    if not number.isdigit():
        return "not digits"
    if len(number) < 13:
        return "short"
    if number.startswith("4"):
        return "four"
    return "other"
