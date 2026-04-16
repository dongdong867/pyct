"""String similarity classification benchmark target.

Category: Solver hard — character-level string comparison
Intent: Compare two strings using multiple similarity measures and classify the relationship
Challenge: The solver must reason about character-level string operations (sorting for
    anagram detection, reversal, prefix/suffix/substring containment, and edit distance).
    These operations create constraints that are difficult for SMT solvers to handle
    because they require reasoning about string contents rather than just length or equality.
"""

from __future__ import annotations


def _check_containment(s1: str, s2: str) -> str | None:
    """Check prefix, suffix, and substring relationships between two strings."""
    if s1.startswith(s2) or s2.startswith(s1):
        return "prefix_match"
    if s1.endswith(s2) or s2.endswith(s1):
        return "suffix_match"
    if s2 in s1 or s1 in s2:
        return "substring_match"
    return None


def _check_anagram(s1: str, s2: str) -> bool:
    """Return True if s1 and s2 are anagrams (same length, same sorted chars)."""
    if len(s1) != len(s2):
        return False
    return sorted(s1) == sorted(s2)


def _compute_simple_distance(s1: str, s2: str) -> int:
    """Compute a simple edit distance approximation.

    For same-length strings, count character differences at each position.
    For different-length strings, use the length difference as the base distance
    plus character differences in the overlapping portion.
    """
    min_len = min(len(s1), len(s2))
    diff_count = abs(len(s1) - len(s2))
    for i in range(min_len):
        if s1[i] != s2[i]:
            diff_count += 1
    return diff_count


def _classify_by_distance(distance: int) -> str:
    """Classify the relationship based on edit distance."""
    if distance <= 1:
        return "near_match"
    if distance <= 3:
        return "similar"
    return "different"


def string_similarity_classification(s1: str, s2: str) -> str:
    """Compare two strings and return a similarity classification."""
    if len(s1) == 0 or len(s2) == 0:
        return "empty_input"

    if s1 == s2:
        return "exact_match"

    if s1.lower() == s2.lower():
        return "case_insensitive_match"

    if s1 == s2[::-1]:
        return "reversed_match"

    containment = _check_containment(s1, s2)
    if containment is not None:
        return containment

    if _check_anagram(s1, s2):
        return "anagram"

    distance = _compute_simple_distance(s1, s2)
    return _classify_by_distance(distance)
