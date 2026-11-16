"""Classes whose methods, properties and special methods each write a file of their own name in
the folder PYCT_TEST_HOOKS names, if any, so a test sees whether one ran. `charge` never touches
its object."""

import os


def charge(order, s):
    if float(s) == 1e-30:
        return 1
    return 0


def touched(name):
    folder = os.environ.get("PYCT_TEST_HOOKS")
    if folder is not None:
        with open(os.path.join(folder, name), "a") as log:
            log.write(f"{os.getpid()}\n")


class Loud:
    def __init__(self, code, peer=None):
        self.code = code
        self.peer = peer

    def cancel(self):
        touched("cancel")
        return 1

    def save(self):
        touched("save")
        return 1

    @property
    def total(self):
        touched("total")
        return 1

    def __getattr__(self, name):
        touched("__getattr__")
        return 1

    def __eq__(self, other):
        touched("__eq__")
        return False

    def __ne__(self, other):
        touched("__ne__")
        return True

    def __lt__(self, other):
        touched("__lt__")
        return False

    def __gt__(self, other):
        touched("__gt__")
        return False

    def __len__(self):
        touched("__len__")
        return 1

    def __bool__(self):
        touched("__bool__")
        return True

    def __str__(self):
        touched("__str__")
        return "s"

    def __repr__(self):
        touched("__repr__")
        return "r"

    def __hash__(self):
        touched("__hash__")
        return 1

    def __iter__(self):
        touched("__iter__")
        return iter([1])

    def __contains__(self, item):
        touched("__contains__")
        return True

    def __index__(self):
        touched("__index__")
        return 1

    def __getitem__(self, key):
        touched("__getitem__")
        return 1

    def __float__(self):
        touched("__float__")
        return 1.0

    def __int__(self):
        touched("__int__")
        return 1

    def __add__(self, other):
        touched("__add__")
        return 1

    def __radd__(self, other):
        touched("__radd__")
        return 1


class Prop:
    def __init__(self, code):
        self.stored = code

    @property
    def code(self):
        touched("code")
        return self.stored


class Hooked:
    def __get__(self, obj, owner=None):
        touched("__get__")
        return "0"

    def __set__(self, obj, value):
        touched("__set__")


class Described:
    code = Hooked()

    def __init__(self, code):
        self.stored = code


class Answering:
    def __init__(self, code):
        self.stored = code

    def __getattr__(self, name):
        touched("__getattr__")
        return "0"


class Gated:
    def __init__(self, code):
        self.code = code

    def __getattribute__(self, name):
        touched("__getattribute__")
        return object.__getattribute__(self, name)


class ClassCode:
    code = "0"

    def __init__(self, code):
        self.stored = code


class Shown:
    def __init__(self, code):
        self.code = code

    def __repr__(self):
        touched("__repr__")
        return "r"

    def __str__(self):
        touched("__str__")
        return "s"
