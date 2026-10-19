"""Hull identity and person-name handling, driven by the reviewed tables in ``data/identity/``.

A hull's key is its sail number's digits with leading zeros stripped; ``aliases.csv`` maps
known typos, renumbers and PHRF numbers onto one hull, each with a recorded reason.
``optout.csv`` removes or corrects a person's name at build time.
"""

from __future__ import annotations

import collections
import csv
import difflib
import re
from collections.abc import Callable, Iterable
from functools import cache
from pathlib import Path
from typing import Any

from j105.http import ROOT

TABLES = ROOT / "data" / "identity"
REMOVED = "(name withheld)"


def _rows(name: str, root: Path = TABLES) -> list[dict[str, str]]:
    path = root / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


@cache
def aliases() -> dict[str, str]:
    return {r["sail"]: r["hull"] for r in _rows("aliases.csv")}


@cache
def splits() -> dict[str, list[tuple[str, str]]]:
    """Sail key -> [(normalized boat name, hull key)] where one number is two hulls."""
    out: dict[str, list[tuple[str, str]]] = {}
    for r in _rows("split_numbers.csv"):
        out.setdefault(r["sail"], []).append((_norm(r["boat"]), r["hull"]))
    return out


@cache
def nicknames() -> dict[str, str]:
    return {r["printed"].lower(): r["name"] for r in _rows("nicknames.csv")}


@cache
def optouts() -> dict[str, tuple[str, str]]:
    return {r["printed"].lower(): (r["action"], r["replacement"]) for r in _rows("optout.csv")}


def sail_key(sail: str) -> str:
    """Digits of a sail number, leading zeros stripped: ``"USA 0475"`` -> ``"475"``.

    Falls back to the stripped text when there are no digits, so nothing is merged by accident.
    """
    digits = re.sub(r"\D", "", sail.split("(")[0]).lstrip("0")
    return digits or sail.strip()


def hull(sail: str, table: dict[str, str] | None = None, boat: str = "") -> str:
    """Hull key for a printed sail, following aliases (a typo of a PHRF number, say) to the end.

    ``boat`` picks the hull when ``split_numbers.csv`` says one number is carried by two hulls
    (e.g. ``7105-speedplay``); a split row matches when its name starts the printed name.
    """
    table = aliases() if table is None else table
    key, seen = sail_key(sail), set()
    if boat:
        name = _norm(boat)
        for prefix, h in splits().get(key, []):
            if prefix and name.startswith(prefix):
                return h
    while key in table and key not in seen:
        seen.add(key)
        key = table[key]
    return key


def tidy(s: str) -> str:
    """Collapse whitespace and fix ALL CAPS or all-lowercase text to title case."""
    s = re.sub(r"\s+", " ", s).strip(" .,/")
    return s.title() if s and (s.isupper() or s.islower()) else s


def person(printed: str) -> str:
    """A skipper name as published, with nicknames resolved and opt-outs applied."""
    p = tidy(printed)
    for nick, name in nicknames().items():
        if nick in p.lower():
            p = name
            break
    action, replacement = optouts().get(p.lower(), ("", ""))
    if action == "remove":
        return REMOVED
    if action == "replace":
        return replacement
    return p


PLACEHOLDER = re.compile(r"(?i)^(tbd|tba|na|n/a|none|\?+|0*)$")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def candidates(events: list[dict]) -> dict[str, list[dict]]:
    """Alias candidates across sources, for a human to review (nothing is merged here).

    ``boat_id``: one Yacht Scoring ``boatId`` under several hull keys (strong evidence of one
    hull). ``name_skipper``: one boat name and skipper under several keys. ``shared_number``:
    one key carried by different boat names and skippers in different regions the same year.
    """
    from j105.regions import event_state, region

    rows = []
    for e in events:
        if not e.get("scored"):
            continue
        for r in e["results"]:
            if not r["sail"] or PLACEHOLDER.match(r["sail"].strip()):
                continue
            rows.append(
                {
                    "key": hull(r["sail"], boat=r["boat"]),
                    "boat": tidy(r["boat"]),
                    "skipper": tidy(r["skipper"]),
                    "year": (e.get("start") or "")[:4],
                    "region": region(event_state(e)),
                    "ys_boat": r.get("ys_boat"),
                    "url": e["url"],
                    "event": e["name"],
                }
            )
    out: dict[str, list[dict]] = {
        "boat_id": [],
        "name_skipper": [],
        "shared_number": [],
        "unnumbered": _unnumbered(events, rows),
    }

    def group(keyf: Callable[[dict], Any]) -> dict[Any, list[dict]]:
        g: dict[Any, list[dict]] = {}
        for r in rows:
            k = keyf(r)
            if k:
                g.setdefault(k, []).append(r)
        return g

    for bid, rs in group(lambda r: r["ys_boat"]).items():
        keys = {r["key"] for r in rs}
        if len(keys) > 1:
            out["boat_id"].append({"ys_boat": bid, **_summary(rs)})
    for rs in group(lambda r: (_norm(r["boat"]), _norm(r["skipper"]))
                    if r["boat"] and r["skipper"] else None).values():  # fmt: skip
        if len({r["key"] for r in rs}) > 1:
            out["name_skipper"].append(_summary(rs))
    for (k, y), rs in group(lambda r: (r["key"], r["year"])).items():
        # One hull often sails under a second name locally (a women's or doublehanded team);
        # different boats in different regions the same year are the Kinetic #401/#440 case.
        regions = {r["region"] for r in rs if r["region"]}
        if (
            len(regions) > 1
            and _distinct(r["boat"] for r in rs) > 1
            and _distinct(r["skipper"] for r in rs) > 1
        ):
            out["shared_number"].append({"key": k, "year": y, **_summary(rs)})
    return out


def _unnumbered(events: list[dict], rows: list[dict]) -> list[dict]:
    """Results printed without a sail number, with the hulls of that boat name within 3 years.

    A match goes in ``unnumbered.csv`` only after review: one name can be two hulls.
    """
    by_name: dict[str, collections.Counter] = {}
    for r in rows:
        if r["boat"] and r["year"]:
            by_name.setdefault(_norm(r["boat"]), collections.Counter())[(r["key"], r["year"])] += 1
    out = []
    for e in events:
        y = int((e.get("start") or "0")[:4] or 0)
        for r in e["results"]:
            if r["sail"] or not r["boat"]:
                continue
            near = collections.Counter()
            for (k, yr), n in by_name.get(_norm(r["boat"]), {}).items():
                if abs(int(yr) - y) <= 3:
                    near[k] += n
            out.append({"event": f"{e['source']}:{e['event_id']}", "year": y,
                        "boat": tidy(r["boat"]), "skipper": tidy(r["skipper"]),
                        "hulls": dict(near.most_common(3)), "example": e["url"]})  # fmt: skip
    return out


def _distinct(names: Iterable[str]) -> int:
    """Clusters of names that differ beyond spelling ("Moose Unknown" ~ "Moose Unknown 2")."""
    reps: list[str] = []
    for n in sorted({_norm(x) for x in names if x}, key=len):
        if not any(r in n or difflib.SequenceMatcher(None, r, n).ratio() > 0.75 for r in reps):
            reps.append(n)
    return len(reps)


def _summary(rs: list[dict]) -> dict:
    by_key: dict[str, collections.Counter] = {}
    for r in rs:
        by_key.setdefault(r["key"], collections.Counter())[
            (r["boat"], r["skipper"], r["region"], r["year"])
        ] += 1
    return {
        "keys": {
            k: [f"{b} / {s} / {reg or '?'} {y} x{n}" for (b, s, reg, y), n in c.most_common(4)]
            for k, c in by_key.items()
        },  # fmt: skip
        "example": rs[0]["url"],
    }
