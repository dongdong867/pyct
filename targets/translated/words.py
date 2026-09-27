import builtins


def greet() -> str:
    # `_` is a name gettext.install puts in builtins after this module loaded
    return _("hello")  # noqa: F821  # pyrefly: ignore[unknown-name]


def shout() -> str:
    # a name this module writes through its own __builtins__, as plain Python writes it for all
    __builtins__["_shouted"] = "HI"  # pyrefly: ignore[unsupported-operation]
    return builtins._shouted  # pyrefly: ignore[missing-attribute]
