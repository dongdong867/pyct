"""What the scans for `own` share: whether a method reaches its base type through the helper."""

from collections.abc import Collection


def reaches_through_the_helper(function: object) -> bool:
    """Whether a function calls `own`, or holds a function that does, the way a closure does."""
    code = getattr(function, "__code__", None)
    if code is None:
        return False
    if "own" in code.co_names:
        return True
    held = [cell.cell_contents for cell in getattr(function, "__closure__", None) or ()]
    return any(reaches_through_the_helper(inner) for inner in held)


def written_in(cls: type, files: Collection[str]) -> dict[str, object]:
    """The members of a class whose code sits in one of these files, by name."""
    return {
        name: member
        for name, member in vars(cls).items()
        if (code := getattr(member, "__code__", None)) is not None and code.co_filename in files
    }


def without_the_helper(cls: type, files: Collection[str]) -> set[str]:
    """The members written in these files that never reach `own`, held closures included."""
    return {
        name
        for name, member in written_in(cls, files).items()
        if not reaches_through_the_helper(member)
    }
