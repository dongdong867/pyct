"""Functions whose arguments are objects a seed names with ``"__class__"``, each class a bare
name here too."""

import datetime
import pathlib

from targets.classes.customers import *  # noqa: F403


def greet(c):
    if c.age > 60:
        return "welcome back"
    return "hello"


def older(p):
    if p.age > 60:
        return "older"
    return "younger"


def left_is_big(q):
    if q.left > 5:
        return "big"
    return "small"


def is_a_date(d):
    if not isinstance(d, datetime.date):
        raise TypeError("not a date")
    return d.year


def visit(c):
    c.visits.append(1)
    if len(c.visits) > 1:
        raise RuntimeError("visited twice")
    if c.age > 60:
        return "senior"
    return "regular"


def kind_of(d):
    if not isinstance(d, dict):
        raise TypeError("not a dict")
    if "k" in d and d["k"] > 1:
        return "many"
    return "few"


def placed(p):
    if p.x > 5:
        return "right"
    return "left"


def suffix_of(f):
    if not isinstance(f, pathlib.Path):
        raise TypeError("not a path")
    # a tracked str in a path's parts stops pathlib, which interns each part as it reads them
    return "path"


def ship(o):
    if o.customer.age > 60:
        return "care"
    return "standard"


def label(t):
    if len(t.extra) > 1:
        return "many"
    if t.names[0] == "x":
        return "x"
    return "other"


def charge(a):
    if a.plan == "pro":
        return 0
    if a.limit > 100:
        return 1
    return 2


def oldest(rows):
    if rows[0]["c"].age > 60:
        return "senior"
    return "regular"


def by_name(d):
    if d["ann"].age > 60:
        return "senior"
    return "regular"


def crowd(cs, d):
    if len(cs) > 1:
        return "crowd"
    if "bob" in d:
        return "bob"
    if cs[0].age > 60:
        return "senior"
    return "few"


def longer(cs):
    if len(cs[1]) > 2:
        return "long"
    return "short"
