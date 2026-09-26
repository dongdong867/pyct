from typing import Any


def echo_any(cfg: dict[str, Any], xs: list[int | None]) -> tuple[dict[str, Any], list[int | None]]:
    return cfg, xs
