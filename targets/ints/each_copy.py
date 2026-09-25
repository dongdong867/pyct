import copy
import dataclasses


@dataclasses.dataclass
class Box:
    value: int


def count(n: int) -> int:
    hits = 0
    if copy.copy(n) > 10:
        hits += 1
    if copy.deepcopy(n) > 20:
        hits += 1
    if dataclasses.asdict(Box(n))["value"] > 30:
        hits += 1
    if copy.copy(n > 40):
        hits += 1
    if copy.deepcopy(n > 50):
        hits += 1
    if dataclasses.asdict(Box(n > 60))["value"]:
        hits += 1
    return hits
