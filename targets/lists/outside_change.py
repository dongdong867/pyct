import heapq


def check(items):
    heapq.heappush(items, 0)
    if items[0] > 5:
        return "big"
    return "small"
