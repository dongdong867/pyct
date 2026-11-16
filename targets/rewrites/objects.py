import os


def pay(order):
    if float(order.code) == 1e-30:
        return 1
    return 0


def pay_hinted(order: "Order"):
    if float(order.code) == 1e-30:
        return 1
    return 0


def tagged(order):
    if float(order.tags[0]) == 1e-30:
        return 1
    return 0


def first(orders, s):
    if float(orders[0].code) == 1e-30:
        return 1
    return 0


def owned(account):
    if float(account.owner.code) == 1e-30:
        return 1
    return 0


def pay_then(order, n):
    if float(order.code) == 1e-30:
        if n > 0:
            return 2
        return 1
    return 0


def pick(order):
    for word in ["2", "1"]:
        if order.code.startswith(word) and float(order.code) == 1e-30:
            return word
    return ""


class Order:
    def __init__(self, code):
        self.code = code


class Till:
    def __init__(self, code):
        self.code = code

    def pay(self):
        if float(self.code) == 1e-30:
            return 1
        return 0


class Tagged:
    def __init__(self, tags):
        self.tags = tags


class Trimmed:
    def __init__(self, code):
        if code.startswith(" "):
            code = code.strip()
        self.code = code.upper()


class Slotted:
    __slots__ = ("code",)

    def __init__(self, code):
        self.code = code


class Statused:
    def __init__(self, code):
        self.code = code
        self.status = "new"


class Code(str):
    pass


class Coded:
    def __init__(self, code):
        self.code = Code(code)


class Account:
    def __init__(self, owner):
        self.owner = owner


class Noisy:
    """Its constructor appends the process id to the file PYCT_TEST_NOISY_LOG names, if any."""

    def __init__(self, code):
        log = os.environ.get("PYCT_TEST_NOISY_LOG")
        if log is not None:
            with open(log, "a") as opened:
                opened.write(f"{os.getpid()}\n")
        self.code = code
