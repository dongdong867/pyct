"""Compare the lines v2 and legacy cover in each target's own body.

``uv run python -m tools.compare_coverage --legacy DIR`` runs every target in ``targets.json``
through this checkout's ``pyct run`` and through legacy's engine in DIR, a checkout of ``main``
with its own environment, one target at a time, with the same seed and limits.
"""
