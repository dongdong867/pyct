"""Functions whose arguments are objects of models.py's classes, which this module never imports.
It holds a library's class, `date`. No hint anywhere."""

from datetime import date


def greet(c):
    if c.age > 60:
        return "welcome back"
    return "hello"


def seniors(cs):
    count = 0
    for c in cs:
        if c.age > 60:
            count += 1
    if count > 1:
        return "crowd"
    return "few"


def pay(o):
    if o.customer.age > 60:
        return "care"
    return "standard"
