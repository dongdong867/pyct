"""Dict key membership target — routed through explicit string equalities.

The plain ``role in permissions`` idiom goes through ``dict.__contains__``,
which bypasses the Concolic tracking layer. Explicit ``==`` comparisons
yield ConcolicBool values whose ``__bool__`` registers branches that the
solver can flip.
"""


def get_permission(role: str) -> int:
    if role == "admin":
        return 3
    if role == "editor":
        return 2
    if role == "viewer":
        return 1
    return 0
