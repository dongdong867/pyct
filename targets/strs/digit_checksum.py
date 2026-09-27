def checksum(number: str) -> str:
    if not number.isdigit():
        return "not digits"
    total = 0
    for at, digit in enumerate(reversed(number)):
        value = int(digit)
        if at % 2 == 1:
            value = value * 2
            if value > 9:
                value = value - 9
        total = total + value
    if total % 10 == 0:
        return "valid"
    return "invalid"
