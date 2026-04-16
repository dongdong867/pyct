"""Shipping rate calculator based on weight, zone, and delivery speed.

Category: mixed_type_synergy
Intent: Classify a shipment into a rate tier by combining an integer weight
    with string-valued zone and speed parameters.  Guards reject invalid or
    out-of-range inputs; specific zone-speed combinations yield named tiers.
Challenge: ~16 branches arise from three zones, three speeds, weight
    thresholds, and special-case combinations (e.g. free domestic standard for
    light parcels, international express premium).  The concolic tester must
    jointly satisfy string-equality and integer-range constraints.
"""

from __future__ import annotations

_VALID_ZONES = frozenset({"domestic", "regional", "international"})
_VALID_SPEEDS = frozenset({"standard", "express", "overnight"})
_MAX_WEIGHT = 1000
_FREE_SHIPPING_WEIGHT = 2


def shipping_rate_calculator(weight: int, zone: str, speed: str) -> str:
    """Return a shipping-rate tier label for the given shipment parameters."""
    if weight <= 0:
        return "invalid_weight"

    if weight > _MAX_WEIGHT:
        return "oversized"

    if zone not in _VALID_ZONES:
        return "invalid_zone"

    if speed not in _VALID_SPEEDS:
        return "invalid_speed"

    if _qualifies_for_free_shipping(weight, zone, speed):
        return "free_shipping"

    return _rate_tier(weight, zone, speed)


def _qualifies_for_free_shipping(
    weight: int,
    zone: str,
    speed: str,
) -> bool:
    return zone == "domestic" and speed == "standard" and weight <= _FREE_SHIPPING_WEIGHT


def _rate_tier(weight: int, zone: str, speed: str) -> str:
    if zone == "international" and speed == "express":
        return "international_express"

    if zone == "international" and speed == "overnight":
        return "overnight_premium"

    if speed == "overnight":
        return "overnight_premium"

    if speed == "express":
        return "express_rate"

    # standard speed from here
    if zone == "international":
        return _international_standard(weight)

    if zone == "regional":
        return "standard_rate"

    # domestic standard (weight > _FREE_SHIPPING_WEIGHT, handled above)
    return _domestic_standard(weight)


def _international_standard(weight: int) -> str:
    if weight > 50:
        return "premium_rate"
    return "standard_rate"


def _domestic_standard(weight: int) -> str:
    if weight > 30:
        return "premium_rate"
    return "economy"
