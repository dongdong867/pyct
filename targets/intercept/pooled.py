from multiprocessing import get_context


def sizes(s: str) -> str:
    # each worker is a fresh interpreter, handed `len` by pickling it
    with get_context("spawn").Pool(1) as pool:
        counts = pool.map(len, [s, "abc"])
    if counts[1] == 3:
        return "pooled"
    return "other"
