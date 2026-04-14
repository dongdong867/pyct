"""Dict key membership target — branching on key presence and absence."""


def get_permission(role: str) -> int:
    permissions = {"admin": 3, "editor": 2, "viewer": 1}
    if role in permissions:
        return permissions[role]
    return 0
