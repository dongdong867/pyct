import copy
import pickle


def f(n: int, xs: list[int]) -> list[str]:
    a = copy.copy(n)
    b = copy.deepcopy(n > 0)
    c = copy.copy(xs)
    d = pickle.loads(pickle.dumps(n))
    e = pickle.loads(pickle.dumps(xs))
    seen = []
    if a > 10:
        seen.append("a")
    if b:
        seen.append("b")
    if len(c) > 2:
        seen.append("c")
    if d > 10:
        seen.append("d")
    if len(e) > 2:
        seen.append("e")
    return seen
