import copy


def check(name: str) -> str:
    backup = copy.deepcopy({"name": name})
    if backup["name"] == "admin":
        return "welcome"
    return "hello"
