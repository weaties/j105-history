"""Command line: ``j105 discover|collect <source>`` and ``j105 counts|hosts|verify``."""

from __future__ import annotations

import argparse
import collections
import logging
from collections.abc import Callable
from typing import Any

from j105.http import RAW, read_json
from j105.regions import event_state, host_key, host_table, region, state_code
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
        _table("region", evs, lambda e: region(event_state(e)) or "unknown")


def hosts() -> None:
    """Seed rows for ``host_clubs.csv`` and the scored events whose state is still unknown.

    A host gets a ``source`` row only when every Clubspot/Yacht Scoring event it ran prints the
    same state. Review the rows before adding them: a generic name ("Corinthian Yacht Club")
    can belong to clubs in several states; pin such events with an ``event`` row instead.
    """
    evs = [e for name in SOURCES for e in read_json(RAW / f"{_short(name)}_events.json", [])]
    seen: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    printed: dict[str, str] = {}
    for e in evs:
        if e.get("host") and e.get("state"):
            seen[host_key(e["host"])][state_code(e["state"])] += 1
            printed.setdefault(host_key(e["host"]), e["host"])
    by_host, _ = host_table()
    print("host,event,state,status,note")
    for key, states in sorted(seen.items()):
        if key in by_host:
            continue
        note = ", ".join(f"{s} {n}" for s, n in states.most_common())
        if len(states) == 1:
            print(f'"{printed[key]}",,{next(iter(states))},source,"Clubspot/YS events: {note}"')
        else:
            print(f'"{printed[key]}",,,proposed,"Clubspot/YS disagree: {note}"')
    missing: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for e in evs:
        if _usable(e) and not event_state(e):
            missing[e.get("host") or ""].append(e)
    print(f"\n{sum(map(len, missing.values()))} scored events with no state, by host:")
    for host, es in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        ex = es[0]
        print(f"  {len(es):3} {host!r}  e.g. {ex['source']}:{ex['event_id']} {ex['name']!r}")


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
    sub.choices["discover"].add_argument(
        "--designs",
        action="store_true",
        help="yachtscoring: instead of the splits scan, scan unindexed events' results for "
        "J/105-design boats in PHRF/ORC/mixed classes",
    )
    c = sub.add_parser("counts")
    c.add_argument("source", nargs="?", choices=list(SOURCES))
    sub.add_parser("hosts")
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
    if a.cmd == "hosts":
        hosts()
        return
    if a.cmd == "verify":
        raise SystemExit(1 if verify() else 0)
    for name in SOURCES if a.source == "all" else [a.source]:
        mod = SOURCES[name]
        if a.cmd == "discover":
            if a.designs and name == "yachtscoring":
                yachtscoring.discover_designs()
            else:
                mod.discover()
        else:
            mod.standings()
            counts(name)


if __name__ == "__main__":
    main()
