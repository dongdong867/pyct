def same(x: int) -> str:
    # nothing is ever unequal to itself, so the solver answers unsat
    if x != x:
        return "never"
    return "always"
