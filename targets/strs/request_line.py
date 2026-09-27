def method(line: str) -> str:
    parts = line.split(" ")
    if parts[0] == "GET":
        return "get"
    return "other"
