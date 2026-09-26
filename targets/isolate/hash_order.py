NAMES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa"]


def place(x: int) -> str:
    # where three names land in a set's order, which follows the interpreter's string hashes
    order = list(set(NAMES))
    for name in ("alpha", "beta", "gamma"):
        if x == order.index(name):
            return name
    return "none"
