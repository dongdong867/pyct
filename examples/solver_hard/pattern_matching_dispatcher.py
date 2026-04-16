"""Pattern matching dispatcher benchmark target.

Category: Solver hard — glob-style pattern interpretation and matching
Intent: Implement simplified glob-style pattern matching and classify the match result
Challenge: The solver must reason about wildcard semantics ('*', '?'), character class
    syntax ('[abc]'), and how pattern structure determines match strategy. Generating
    inputs that reach specific match outcomes requires the solver to coordinate pattern
    syntax with text content — a character-level reasoning task that SMT solvers
    struggle with because wildcard expansion is not a native constraint theory.
"""

from __future__ import annotations


def _match_extension(pattern: str, text: str) -> str:
    """Handle patterns of the form '*.ext'."""
    extension = pattern[1:]
    if text.endswith(extension):
        return "extension_match"
    return "no_match"


def _match_prefix(pattern: str, text: str) -> str:
    """Handle patterns of the form 'prefix*'."""
    prefix = pattern[:-1]
    if text.startswith(prefix):
        return "prefix_match"
    return "no_match"


def _match_contains(pattern: str, text: str) -> str:
    """Handle patterns of the form '*middle*'."""
    middle = pattern[1:-1]
    if len(middle) == 0:
        return "match_all"
    if middle in text:
        return "contains_match"
    return "no_match"


def _match_single_wildcard(pattern: str, text: str) -> str:
    """Handle patterns with exactly one '?' wildcard."""
    if len(pattern) != len(text):
        return "no_match"
    for i in range(len(pattern)):
        if pattern[i] == "?":
            continue
        if pattern[i] != text[i]:
            return "no_match"
    return "full_match"


def _classify_wildcard_pattern(pattern: str, text: str) -> str:
    """Route a wildcard-containing pattern to the appropriate matcher."""
    star_count = pattern.count("*")
    question_count = pattern.count("?")

    if star_count == 0 and question_count == 1:
        return _match_single_wildcard(pattern, text)

    if star_count == 1 and pattern.startswith("*"):
        return _match_extension(pattern, text)

    if star_count == 1 and pattern.endswith("*"):
        return _match_prefix(pattern, text)

    if star_count == 2 and pattern.startswith("*") and pattern.endswith("*"):
        return _match_contains(pattern, text)

    return "complex_pattern"


def _has_character_class(pattern: str) -> bool:
    """Check if pattern contains a character class like [abc]."""
    open_pos = pattern.find("[")
    if open_pos < 0:
        return False
    close_pos = pattern.find("]", open_pos + 1)
    return close_pos > open_pos + 1


def pattern_matching_dispatcher(pattern: str, text: str) -> str:
    """Match a glob-style pattern against text and return a classification."""
    if len(pattern) == 0 or len(text) == 0:
        return "empty_input"

    if pattern == "*":
        return "match_all"

    if _has_character_class(pattern):
        return "class_pattern"

    has_wildcard = "*" in pattern or "?" in pattern
    if not has_wildcard:
        if pattern == text:
            return "full_match"
        return "no_match"

    return _classify_wildcard_pattern(pattern, text)
