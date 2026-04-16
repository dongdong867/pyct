"""Discount engine combining coupon codes with quantity-based pricing.

Category: mixed_type_synergy
Intent: Compute a final order classification after applying a coupon code
    (string) and quantity-based bulk discounts to a unit price (integer) and
    quantity (integer).
Challenge: ~18 branches stem from the interplay of six coupon codes, three
    quantity tiers, and several edge-case guards.  The concolic tester must
    jointly satisfy string-equality constraints on the coupon and integer
    range constraints on price, quantity, and the derived total.
"""

from __future__ import annotations

_COUPON_PERCENT: dict[str, int] = {
    "SAVE10": 10,
    "SAVE20": 20,
    "HALF": 50,
}

_FLAT_DISCOUNT = 50
_WHOLESALE_QTY = 100
_BULK_QTY = 10
_WHOLESALE_DISCOUNT_PERCENT = 15
_BULK_DISCOUNT_PERCENT = 5


def discount_engine(price: int, quantity: int, coupon: str) -> str:
    """Classify an order by its post-discount total.

    *price* is the unit price in dollars.  *quantity* is the item count.
    *coupon* is one of the recognised coupon codes or ``""`` / ``"NONE"``.
    """
    if price < 0 or quantity < 0:
        return "invalid_negative"

    if price == 0:
        return "free_item"

    if quantity == 0:
        return "empty_cart"

    coupon_result = _apply_coupon(price, quantity, coupon)
    if coupon_result is None:
        return "invalid_coupon"

    subtotal = coupon_result
    total = _apply_quantity_discount(subtotal, quantity)
    return _classify_total(total)


def _apply_coupon(price: int, quantity: int, coupon: str) -> int | None:
    subtotal = price * quantity

    if coupon in ("", "NONE"):
        return subtotal

    if coupon in _COUPON_PERCENT:
        discount = subtotal * _COUPON_PERCENT[coupon] // 100
        return subtotal - discount

    if coupon == "BOGOF":
        if quantity < 2:
            return subtotal  # BOGOF requires 2+; no discount applied
        free_items = quantity // 2
        return price * (quantity - free_items)

    if coupon == "FLAT50":
        return max(0, subtotal - _FLAT_DISCOUNT)

    return None  # unrecognised coupon


def _apply_quantity_discount(subtotal: int, quantity: int) -> int:
    if quantity >= _WHOLESALE_QTY:
        return subtotal - subtotal * _WHOLESALE_DISCOUNT_PERCENT // 100
    if quantity >= _BULK_QTY:
        return subtotal - subtotal * _BULK_DISCOUNT_PERCENT // 100
    return subtotal


def _classify_total(total: int) -> str:
    if total <= 0:
        return "free_after_discount"
    if total < 50:
        return "small_order"
    if total < 200:
        return "medium_order"
    if total < 1000:
        return "large_order"
    return "bulk_order"
