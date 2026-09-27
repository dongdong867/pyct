# one change per function, each on a fresh copy of the argument, then a fork on an item of the
# result against a literal. Seed each with [1, 2, 3, 4, 5, 6].


def appended(items):
    a = items.copy()
    a.append(7)
    if a[6] == 0:
        return 1
    return 0


def extended(items):
    a = items.copy()
    a.extend([7, 8])
    if a[7] == 0:
        return 1
    return 0


def inserted(items):
    a = items.copy()
    a.insert(1, 7)
    if a[2] == 0:
        return 1
    return 0


def popped(items):
    a = items.copy()
    a.pop()
    if a[-1] == 0:
        return 1
    return 0


def removed(items):
    a = items.copy()
    a.remove(2)
    if a[1] == 0:
        return 1
    return 0


def assigned(items):
    a = items.copy()
    a[1] = 7
    if a[2] == 0:
        return 1
    return 0


def deleted(items):
    a = items.copy()
    del a[1]
    if a[1] == 0:
        return 1
    return 0


def deleted_slice(items):
    a = items.copy()
    del a[1:3]
    if a[1] == 0:
        return 1
    return 0


def assigned_slice(items):
    a = items.copy()
    a[1:3] = [7]
    if a[2] == 0:
        return 1
    return 0


def reversed_in_place(items):
    a = items.copy()
    a.reverse()
    if a[0] == 0:
        return 1
    return 0


def sorted_in_place(items):
    a = items.copy()
    a.sort()
    if a[0] == 0:
        return 1
    return 0


def copied(items):
    a = items.copy()
    if a[0] == 0:
        return 1
    return 0


def added(items):
    a = items + [7]
    b = [8] + items
    if a[1] == 0 or b[1] == 0:
        return 1
    return 0


def added_in_place(items):
    a = items.copy()
    a += [7]
    if a[1] == 0:
        return 1
    return 0


def repeated(items):
    a = items * 2
    b = 2 * items
    if a[7] == 0 or b[0] == 0:
        return 1
    return 0


def repeated_in_place(items):
    a = items.copy()
    a *= 2
    if a[6] == 0:
        return 1
    return 0


def sliced(items):
    a = items[1:4]
    b = items[::-1]
    if a[0] == 0 or b[0] == 0:
        return 1
    return 0
