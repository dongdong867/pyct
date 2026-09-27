def card(number: str) -> str:
    digits = number.replace(" ", "")
    if not digits.isdigit():
        return "not digits"
    if len(digits) < 13:
        return "short"
    if digits.startswith("4"):
        return "four"
    return "other"
