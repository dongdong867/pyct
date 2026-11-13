"""Functions that test a dict for the key ``"__class__"``, the key a seed's object form names its
class with, and one that tests for its escaped spelling ``"!__class__"``."""


def has_class(d):
    if "__class__" in d:
        return 1
    return 0


def first_has_class(xs):
    if "__class__" in xs[0]:
        return 1
    return 0


class Box:
    def __init__(self, d):
        self.d = d


def box_has_class(b):
    if "__class__" in b.d:
        return 1
    return 0


class Holder:
    def __init__(self, d):
        self.d = d

    def has(self):
        if "__class__" in self.d:
            return 1
        return 0


def names_box(d):
    if d.get("__class__", "") == "targets.dicts.class_key::Box":
        return 1
    return 0


def has_escaped(d):
    if "!__class__" in d:
        return 1
    return 0


def holds_a_box(box):
    if "__class__" in box and isinstance(box["b"], Box):
        return 1
    return 0


def pair_has_class(pair):
    if "__class__" in pair[0]:
        return 1
    return 0


def kind_of(d):
    if isinstance(d, Box):
        return 1
    return 0
