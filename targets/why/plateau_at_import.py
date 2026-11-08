def helper(x):
    return x > 5
READY = helper(0)
def f(x):
    y = helper(x) if x > 0 else 0
    if y:
        return "big"
    return "small"
