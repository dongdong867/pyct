def check(port: int, x: int) -> str:
    if port in range(1, 65536):
        return "port"
    if x in range(0, 10, 2):
        return "even"
    return "none"
