def check(orders):
    for o in orders:
        if "coupon" in o and o["coupon"] == "SAVE":
            return "saved"
    return "none"
