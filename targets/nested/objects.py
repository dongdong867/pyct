"""Objects a seed given through run() holds, and targets that read their attributes."""

import threading


def checked(value):
    return value


class Rule:
    """A rule whose attributes are an int, a str, and a module-level function."""

    def __init__(self):
        self.limit = 10
        self.label = "x"
        self.check = checked


def classify_rule(rule):
    if rule.limit > 100:
        return "high"
    if rule.limit < 0:
        return "negative"
    if rule.label == "strict":
        return "strict"
    return "plain"


class Counter:
    """An object with one int, which a seed may hand on under two names."""

    def __init__(self):
        self.n = 0


def two_counters(a, b):
    if a.n > 5:
        if b.n > 7:
            return "both"
        return "first"
    return "neither"


class Node:
    """An object that holds itself as an attribute."""

    def __init__(self):
        self.n = 0
        self.me = self


def node_check(node):
    if node.me is node and node.n > 5:
        return "big"
    return "small"


class Holder:
    """An object holding a list and a dict."""

    def __init__(self):
        self.items = [0]
        self.table = {"k": 0}


def held(holder):
    if holder.items[0] > 5:
        return "item"
    if holder.table["k"] > 5:
        return "value"
    return "neither"


class Box:
    """An object deepcopy refuses, for its lock, with an int beside it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.n = 0


def boxed(box):
    if box.n > 5:
        return "big"
    return "small"
