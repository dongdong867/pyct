def order(s, t):
    if s < t:
        if t <= s:
            return "impossible"
        return "below"
    return "not below"
