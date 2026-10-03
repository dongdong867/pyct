import os
import signal


def store_walk(d: dict):
    d["a"] = 0
    count = 0
    for k in d:
        count += 1
    if count > 1:
        return "more"
    return "one"


def tracked_store_walk(n: str, d: dict):
    d[n] = 0
    count = 0
    for k in d:
        count += 1
    if count > 1:
        return "more"
    return "one"


def store_truth(config: dict):
    config["a"] = 0
    if config:
        return 1
    return 0


def looked_up_twice(d: dict):
    n = 0
    if "a" in d:
        n += 1
    if "a" in d:
        n += 2
    return n


def store_if_flag(flag: bool, d: dict):
    if flag:
        d["a"] = 0
    if d:
        return 1
    return 0


def removed_truth(d: dict):
    del d["a"]
    if d:
        return 1
    return 0


def found_truth(d: dict):
    if "a" in d:
        if d:
            return 1
        return 2
    return 0


def store_then_die(config: dict):
    config["a"] = 0
    if config:
        os.kill(os.getpid(), signal.SIGKILL)
    else:
        return 1


def repeat_after_tracked_store(n: str, d: dict):
    if "a" in d:
        return 0
    d[n] = 0
    if "a" in d:
        return 1
    return 2


def walk_after_tracked_pop(n: str, d: dict):
    d["a"] = 5
    if "b" in d:
        d.pop(n, None)
        count = 0
        for k in d:
            count += 1
        if count == 1:
            return "one"
        return "more"
    return "none"


def truth_after_tracked_pop(n: str, d: dict):
    d["zz"] = 1
    del d["zz"]
    if "b" in d:
        d.pop(n, None)
        if d:
            return 1
        return 2
    return 0
