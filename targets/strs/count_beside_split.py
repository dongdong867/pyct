"""A count of a separator beside the pieces a split on it makes."""


def address(email: str):
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    if len(local) > 64 or len(domain) > 255:
        return False
    return True


def fields(line: str):
    if line.count(",") != 2:
        return 0
    first, second, third = line.split(",")
    if len(third) > 40 and first == "id":
        return 1
    return 2
