def pick(s):
    for word in ["2", "1"]:
        if s.startswith(word) and float(s) == 1e-30:
            return word
    return ""
