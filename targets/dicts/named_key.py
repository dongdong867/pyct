def check(order):
    if "coupon" in order:
        return "coupon"
    if order.get("tip", 0) > 10:
        return "tip"
    if order["total"] > 100:
        return "big"
    if order["total"] < 0:
        return "negative"
    return "plain"
