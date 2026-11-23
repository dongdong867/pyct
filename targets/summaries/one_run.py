"""A loop over a call pyct does not follow, so the seed's input records no fork and the moment
after it has one complete run, for the refuse-a-summary-that-only-repeats-its-runs story."""


def z_bytes(s: str) -> str:
    t = 0
    for b in s.encode():
        if b == 122:
            t += 1
    if t > 3:
        return "many"
    return "few"
