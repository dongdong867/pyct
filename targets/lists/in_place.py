def tally(counts, n):
    for _ in range(30):
        counts[0] += 1
    if counts[1] > n:
        return "over"
    return "under"


def swaps(pair):
    for _ in range(10):
        pair[0], pair[1] = pair[1], pair[0]
    if pair[0] > 5:
        return "big"
    return "small"
