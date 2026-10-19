"""Consistency checks on collected standings. Reports problems; never edits data.

Automated checks catch parse and ranking errors. They do not replace spot-checking events
against the official results pages (see the ``verify`` skill).
"""

from __future__ import annotations

import collections
import random
from typing import Any

from j105.http import RAW, read_json
from j105.identity import sail_key

FILES = {"clubspot": "clubspot", "yachtscoring": "ys", "regattanetwork": "rn", "styc": "styc",
         "sailwave": "sailwave",
         "j105org": "j105org"}  # fmt: skip


def check_event(e: dict[str, Any]) -> list[str]:
    problems = []
    res = e["results"]
    if e["fleet"] != len(res):
        problems.append(f"fleet {e['fleet']} != {len(res)} results")
    places = [r["place"] for r in res]
    # Places run 1..n; an unbroken tie repeats a place (10, 10, 10) only where points are equal.
    for i, (r, p) in enumerate(zip(res, places, strict=True)):
        tie = i > 0 and p == places[i - 1] and r.get("net") == res[i - 1].get("net")
        if p != i + 1 and not tie:
            problems.append(f"place {p} at row {i + 1}")
            break
    nets = [r["net"] for r in res if r.get("net") is not None]
    # Low-point scoring: net never falls as place rises. Ties broken by the scorer are fine.
    if e.get("scored") and any(b < a for a, b in zip(nets, nets[1:], strict=False)):
        problems.append("net points fall as place rises")
    sails = collections.Counter(sail_key(r["sail"]) for r in res if r["sail"])
    dup = [s for s, n in sails.items() if n > 1]
    if dup:
        problems.append(f"repeated sail numbers {dup}")
    if not e.get("url"):
        problems.append("no official results URL")
    return problems


def verify(sample: int = 5, seed: int = 105) -> int:
    """Print problems per source and a random sample to check by hand; return problem count."""
    total = 0
    rng = random.Random(seed)
    for source, short in FILES.items():
        evs = [
            e for e in read_json(RAW / f"{short}_events.json", []) if e["fleet"] > 1 and e["scored"]
        ]
        bad = [(e, p) for e in evs if (p := check_event(e))]
        total += len(bad)
        print(f"\n{source}: {len(evs)} events, {len(bad)} with problems")
        for e, p in bad[:15]:
            print(
                f"  {e['start']} {e['name'][:50]!r} [{e['class']}]: {'; '.join(p)}\n    {e['url']}"
            )
        if len(bad) > 15:
            print(f"  … and {len(bad) - 15} more")
        print("  spot-check against the official page:")
        for e in rng.sample(evs, min(sample, len(evs))):
            top = ", ".join(
                f"{r['place']}. {r['sail']} {r['boat']} {r['net']}" for r in e["results"][:3]
            )
            print(
                f"    {e['start']} {e['name'][:45]!r} fleet {e['fleet']}: {top}\n      {e['url']}"
            )
    return total
