import copy
import pickle


def round_trip(n: int) -> str:
    restored = pickle.loads(pickle.dumps(n))
    if restored > 10:
        return "big"
    return "small"


def pickle_then_check(n: int) -> str:
    pickle.dumps(n)
    if n > 10:
        return "big"
    return "small"


def each_type(n: int, s: str) -> list[str]:
    a = pickle.loads(pickle.dumps(n))
    b = pickle.loads(pickle.dumps(n > 0))
    c = pickle.loads(pickle.dumps(s))
    loaded = []
    if type(a) is int and a == 3:
        loaded.append("int")
    if type(b) is bool and b is True:
        loaded.append("bool")
    if type(c) is str and c == "ab":
        loaded.append("str")
    return loaded


def every_protocol(n: int) -> int:
    big = 0
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        restored = pickle.loads(pickle.dumps(n, protocol))
        if restored > 10:
            big += 1
    return big


def in_a_container(n: int, s: str) -> str:
    data = pickle.loads(pickle.dumps({"n": n, "s": s, "k": 1}))
    if data["n"] > 10:
        return "big"
    return "small"


def copied(n: int) -> str:
    m = copy.deepcopy(n)
    if m > 10:
        return "big"
    return "small"


def past_the_highest_protocol(n: int) -> bytes:
    return pickle.dumps(n, protocol=99)
