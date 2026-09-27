"""A sweep fixture: a class whose constructor forks, and two whose constructors are not Python."""


class Cart:
    def __init__(self, owner: str) -> None:
        if owner == "admin":
            self.rights = "all"
        else:
            self.rights = "none"


class Plain:
    pass


class NotFound(ValueError):
    pass
