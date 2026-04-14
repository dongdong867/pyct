"""Target with a provably unreachable branch — solver should report UNSAT."""


def unreachable(x: int) -> int:
    if x != x:  # always false — solver should never satisfy this
        return 1
    return 0
