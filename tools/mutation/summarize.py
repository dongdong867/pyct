"""Summarize mutmut results by module from per-file .meta files."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def summarize(mutants_dir: Path) -> None:
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "killed": 0, "survived": 0, "other": 0}
    )
    for meta_path in mutants_dir.rglob("*.py.meta"):
        rel = meta_path.relative_to(mutants_dir).with_suffix("")
        module = str(rel).replace("/", ".").replace("src.pyct.engine.", "")
        data = json.loads(meta_path.read_text())
        for exit_code in data["exit_code_by_key"].values():
            totals[module]["total"] += 1
            if exit_code == 0:
                totals[module]["survived"] += 1
            elif exit_code is None:
                totals[module]["other"] += 1
            else:
                totals[module]["killed"] += 1

    header = f"{'Module':<35}{'Total':>8}{'Killed':>8}{'Surv.':>8}{'Other':>8}{'Kill%':>8}"
    print(header)
    print("-" * len(header))
    g = {"total": 0, "killed": 0, "survived": 0, "other": 0}
    for mod in sorted(totals):
        s = totals[mod]
        rate = 100 * s["killed"] / s["total"] if s["total"] else 0.0
        print(
            f"{mod:<35}{s['total']:>8}{s['killed']:>8}{s['survived']:>8}{s['other']:>8}{rate:>7.1f}%"
        )
        for k in g:
            g[k] += s[k]
    print("-" * len(header))
    rate = 100 * g["killed"] / g["total"] if g["total"] else 0.0
    print(
        f"{'TOTAL':<35}{g['total']:>8}{g['killed']:>8}{g['survived']:>8}{g['other']:>8}{rate:>7.1f}%"
    )


if __name__ == "__main__":
    summarize(Path("mutants"))
