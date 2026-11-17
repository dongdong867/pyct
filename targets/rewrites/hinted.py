def pay(order: "Order"):
    if float(order.code) == 1e-30:
        return 1
    return 0


def first(orders: "list[Order]"):
    if float(orders[0].code) == 1e-30:
        return 1
    return 0


def charge(order: "Order", s):
    if float(s) == 1e-30:
        return 1
    return 0


class Order:
    def __init__(self, code):
        self.code = code
