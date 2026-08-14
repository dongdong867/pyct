"""Nested-dict argument target.

Every branch reads a primitive buried under two dict levels. Without
per-leaf symbolic naming the whole function runs concretely, so only the
seed's own path is ever reached.

The final branch is deliberately cross-field: it constrains ``workers``
and ``port`` at once, which a per-leaf naming scheme can satisfy but a
whole-dict replacement strategy cannot aim at.
"""

from __future__ import annotations


def validate_config(config: dict) -> str:
    port = config["server"]["port"]
    if port < 1:
        return "port_too_low"
    if port > 65535:
        return "port_too_high"
    workers = config["server"]["workers"]
    if workers > 16 and port == 8080:
        return "high_workers_default_port"
    return "ok"
