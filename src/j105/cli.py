"""Command line: ``j105 discover|collect <source>``, ``j105 counts``, ``j105 verify``."""

from __future__ import annotations

import argparse
import collections
import logging
from collections.abc import Callable
from typing import Any

from j105.http import RAW, read_json
from j105.regions import region
from j105.sources import clubspot, regattanetwork, yachtscoring
from j105.verify import verify

SOURCES: dict[str, Any] = {
    "clubspot": clubspot,
    "yachtscoring": yachtscoring,
    "regattanetwork": regattanetwork,
}


def counts(source: str | None = None) -> None:
    """Print events, boat results and sail numbers per year and per region for each source."""
    for name in [source] if source else SOURCES:
        evs = [e for e in read_json(RAW / f"{_short(name)}_events.json", []) if _usable(e)]
        if not evs:
            print(f"{name}: no events collected")
            continue
        sails = {r["sail"] for e in evs for r in e["results"]}
        print(
            f"\n{name}: {len(evs)} scored J/105 events, "
            f"{sum(e['fleet'] for e in evs)} boat results, {len(sails)} sail numbers"
        )
        _table("year", evs, lambda e: (e.get("start") or "????")[:4])
        _table("region", evs, lambda e: region(e.get("state") or "") or "unknown")


def _usable(e: dict[str, Any]) -> bool:
    return bool(e.get("scored")) and e.get("fleet", 0) > 1


def _table(label: str, evs: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> None:
    ev_n: collections.Counter[str] = collections.Counter()
    res_n: collections.Counter[str] = collections.Counter()
    for e in evs:
        ev_n[key(e)] += 1
        res_n[key(e)] += e["fleet"]
    print(f"  by {label}: " + ", ".join(f"{k} {ev_n[k]}/{res_n[k]}" for k in sorted(ev_n)))


def _short(name: str) -> str:
    return {"yachtscoring": "ys", "regattanetwork": "rn"}.get(name, name)


def main() -> None:
    p = argparse.ArgumentParser(prog="j105", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("discover", "collect"):
        s = sub.add_parser(cmd)
        s.add_argument("source", choices=[*SOURCES, "all"])
    c = sub.add_parser("counts")
    c.add_argument("source", nargs="?", choices=list(SOURCES))
    sub.add_parser("verify")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if a.cmd == "counts":
        counts(a.source)
        return
    if a.cmd == "verify":
        raise SystemExit(1 if verify() else 0)
    for name in SOURCES if a.source == "all" else [a.source]:
        mod = SOURCES[name]
        if a.cmd == "discover":
            mod.discover()
        else:
            mod.standings()
            counts(name)


if __name__ == "__main__":
    main()
