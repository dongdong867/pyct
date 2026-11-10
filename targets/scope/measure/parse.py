def parse(value: int) -> int:
    """A library's own reading of a number: its digits, as int writes them, read back."""
    return int(int.__repr__(value))
