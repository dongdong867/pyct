def touch(items, table):
    if table[1.5] != [0]:
        raise ValueError("an earlier input changed the arguments")
    table[1.5].append(99)
    if items[0] > 5:
        return "big"
    return "small"
