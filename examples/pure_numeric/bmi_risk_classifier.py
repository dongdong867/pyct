"""Body-mass-index risk classifier.

Category: pure_numeric
Intent: Compute BMI from integer height (cm) and weight (kg), then map the
    result to a WHO-style risk category.  Guard clauses reject non-positive
    and physiologically implausible inputs.
Challenge: The BMI formula introduces a non-linear relationship
    (weight / (height/100)^2) that the solver must navigate, combined with
    boundary comparisons on the computed value.  ~12 branches total.
"""

from __future__ import annotations

_BMI_CATEGORIES: list[tuple[float, str]] = [
    (40.0, "obese_class_3"),
    (35.0, "obese_class_2"),
    (30.0, "obese_class_1"),
    (25.0, "overweight"),
    (18.5, "normal"),
    (16.0, "underweight"),
]

_MAX_HEIGHT_CM = 300
_MAX_WEIGHT_KG = 500


def bmi_risk_classifier(height_cm: int, weight_kg: int) -> str:
    """Return a WHO-style BMI risk category for the given measurements."""
    if height_cm <= 0 or weight_kg <= 0:
        return "invalid_non_positive"

    if height_cm > _MAX_HEIGHT_CM:
        return "unrealistic_height"

    if weight_kg > _MAX_WEIGHT_KG:
        return "unrealistic_weight"

    bmi = _compute_bmi(height_cm, weight_kg)
    return _classify_bmi(bmi)


def _compute_bmi(height_cm: int, weight_kg: int) -> float:
    height_m = height_cm / 100.0
    return weight_kg / (height_m * height_m)


def _classify_bmi(bmi: float) -> str:
    for threshold, label in _BMI_CATEGORIES:
        if bmi >= threshold:
            return label
    return "severely_underweight"
