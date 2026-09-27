"""How large an answer may be.

A string in an answer holds at most ``MOST_ITEMS`` characters, and each
program holds every string leaf to it, so a fork only a longer string
takes is unsat. cvc5 is asked to write a string answer in full up to the
same length; past its default, 65,536 characters, it writes a ``witness``
term that names only a length and a counter, not a string. Decisions
answers-hold-at-most-a-million-items and long-strings-written-in-full-by-cvc5.
"""

# the most items a value in an answer holds, such as the characters of a string
MOST_ITEMS = 1_000_000


def longest_string(term: str) -> str:
    """The assertion that holds a string term to the most characters an answer holds."""
    return f"(assert (<= (str.len {term}) {MOST_ITEMS}))"
