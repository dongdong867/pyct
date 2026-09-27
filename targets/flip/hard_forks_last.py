def triage(n: int, s: str, t: str, u: str) -> str:
    sign = "positive"
    if n <= 0:
        sign = "not positive"
    if s < t and t <= s:
        return "impossible"
    if s < u and u <= s:
        return "impossible"
    if t < u and u <= t:
        return "impossible"
    return sign
