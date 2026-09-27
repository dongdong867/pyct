def count_vowels(s: str) -> str:
    count = 0
    for c in s:
        if c in "aeiou":
            count += 1
    if count > 2:
        return "many"
    return "few"
