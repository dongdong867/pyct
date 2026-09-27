def classify(s: str) -> str:
    if s.isdigit():
        if s.isdecimal():
            if s.isnumeric():
                return "digits"
        return "other digits"
    if s.isalpha():
        if s.isupper():
            return "upper word"
        if s.islower():
            return "lower word"
        if s.istitle():
            return "title word"
        return "mixed word"
    if s.isalnum():
        return "letters and digits"
    if s.isidentifier():
        return "name"
    if s.isspace():
        return "space"
    if s.isprintable():
        return "printable"
    if s.isascii():
        return "ascii"
    return "other"
