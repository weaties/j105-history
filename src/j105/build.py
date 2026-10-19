"""Build the site data: every collected event, cleaned, deduped and scored, in one JSON file.

Applied here, never in ``data/raw``: hull identity (aliases, split numbers), skipper nicknames
and opt-outs, host-club states, excluded events. Events that more than one source holds are
merged: the copy from the preferred source is kept and the others' links are listed with it.
"""

from __future__ import annotations

import collections
import datetime as dt
import html
import logging
import re
from typing import Any

from j105.http import RAW, ROOT, read_json, write_json
from j105.identity import PLACEHOLDER, _rows, hull, person, tidy
from j105.regions import event_state, in_scope, region

log = logging.getLogger(__name__)

OUT = ROOT / "site" / "data" / "events.json"
# Preferred copy when sources overlap: richest fields and official scoring first.
SOURCES = {
    "yachtscoring": ("ys", "Yacht Scoring", "https://www.yachtscoring.com"),
    "clubspot": ("clubspot", "Clubspot", "https://theclubspot.com"),
    "regattanetwork": ("rn", "Regatta Network", "https://www.regattanetwork.com"),
    "styc": ("styc", "Sloop Tavern YC", "https://www.styc.org"),
    "sailwave": ("sailwave", "Sailwave", "https://www.sailwave.com"),
    "j105org": ("j105org", "J/105 Class archive", "https://archive.j105.org"),
}
MIN_MIXED = 3  # a mixed event counts toward season scores only with this many J/105s
KINDS = [
    ("North Americans", r"north\s+american"),
    ("NOOD", r"\bnood\b|sailing world regatta series"),
    ("Race week", r"race\s*week|block island|key west|bayweek"),
    ("Big Boat Series", r"big\s*boat"),
    ("Evening & series", r"series|night|wednesday|tuesday|thursday|friday|twilight"
                         r"|beer\s*can|frostbite|midwinter|sunset|season"),
]  # fmt: skip


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _skipper(s: str) -> str:
    """Tidy a printed skipper; collapse a doubled cell ("Richard Butts Richard Butts")."""
    words = _clean(s).split()
    half = len(words) // 2
    if half and len(words) % 2 == 0 and words[:half] == words[half:]:
        words = words[:half]
    return person(" ".join(words))


def _kind(name: str) -> str:
    for label, rx in KINDS:
        if re.search(rx, name, re.I):
            return label
    return "Regatta"


def _day(s: str) -> dt.date:
    """``"1996"`` or ``"1996-09"`` (archive events printed without a day) -> first day."""
    return dt.date.fromisoformat((s + "-01-01"[len(s) - 4 :])[:10] if len(s) < 10 else s)


def _token(*parts: str) -> str:
    return re.sub(r"[^A-Za-z0-9._~-]+", "-", "-".join(parts)).strip("-")[:80]


def _load() -> list[dict[str, Any]]:
    out = []
    for short, _, _ in SOURCES.values():
        for e in read_json(RAW / f"{short}_events.json", []):
            if e.get("scored") and e.get("fleet", 0) >= 1 and in_scope(e) and e.get("start"):
                out.append(e)
    return out


def _event(e: dict[str, Any]) -> dict[str, Any]:
    st = event_state(e)
    results = []
    for r in e["results"]:
        sail = r["sail"].strip()
        h = hull(sail, boat=r["boat"]) if sail and not PLACEHOLDER.match(sail) else ""
        results.append(
            [
                h,
                tidy(_clean(r["boat"])),
                _skipper(r["skipper"]),
                r["place"],
                r.get("net"),
                _clean(r.get("club") or ""),
            ]
        )
    fleet = e["fleet"]
    mixed = bool(e.get("mixed"))
    return {
        "id": _token(SOURCES[e["source"]][0], e["event_id"], e.get("class") or ""),
        "date": e["start"][:10],
        "end": (e.get("end") or e["start"])[:10],
        "name": _clean(e["name"]),
        "class": _clean(e.get("class") or ""),
        "kind": _kind(_clean(e["name"])),
        "source": e["source"],
        "url": e["url"],
        "also": [],
        "state": st,
        "region": region(st) or "Unknown",
        "host": _clean(e.get("host") or ""),
        "fleet": fleet,
        "races": e.get("races") or 0,
        "mixed": mixed,
        "division": e.get("division_size") or 0,
        # Counts toward season scores: a ranked fleet, and enough J/105s in a mixed class.
        "counts": fleet > 1 and (not mixed or fleet >= MIN_MIXED),
        "results": results,
    }


def _keys(e: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Hulls and boat names in an event (names catch results printed without sails)."""
    hulls = {r[0] for r in e["results"] if r[0]}
    names = {re.sub(r"[^a-z0-9]", "", r[1].lower()) for r in e["results"]} - {""}
    return hulls, names


def _overlap(a: set[str], b: set[str]) -> bool:
    return min(len(a), len(b)) >= 2 and len(a & b) >= 0.7 * min(len(a), len(b))


def _dedupe(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Merge the same race held by two sources: dates within 3 days, mostly the same hulls."""
    order = list(SOURCES)
    events.sort(key=lambda e: (e["date"], order.index(e["source"])))
    kept: list[dict[str, Any]] = []
    merged = 0
    for e in events:
        hulls, names = _keys(e)
        d = _day(e["date"])
        dup = None
        for k in reversed(kept[-60:]):
            if (d - _day(k["date"])).days > 3:
                break
            if k["source"] == e["source"] or k["mixed"] != e["mixed"]:
                continue
            kh, kn = _keys(k)
            if _overlap(hulls, kh) or _overlap(names, kn):
                dup = k
                break
        if dup is None:
            kept.append(e)
            continue
        merged += 1
        # Keep the preferred source's copy; list the other copy's link.
        if order.index(e["source"]) < order.index(dup["source"]):
            e["also"] = [*dup["also"], {"source": dup["source"], "url": dup["url"]}]
            kept[kept.index(dup)] = e
        else:
            dup["also"].append({"source": e["source"], "url": e["url"]})
    return kept, merged


def build() -> dict[str, Any]:
    raw = _load()
    events, merged = _dedupe([_event(e) for e in raw])
    events.sort(key=lambda e: (e["date"], e["name"], e["class"]))
    # Ids are deep-link tokens; a repeated division name in one event gets a stable suffix.
    seen: collections.Counter[str] = collections.Counter()
    for e in events:
        seen[e["id"]] += 1
        if seen[e["id"]] > 1:
            e["id"] = f"{e['id']}-{seen[e['id']]}"
    notes = {r["hull"]: r["note"] for r in _rows("hull_notes.csv")}
    data = {
        "generated": dt.date.today().isoformat(),
        "sources": {k: {"name": v[1], "home": v[2]} for k, v in SOURCES.items()},
        "min_mixed": MIN_MIXED,
        "notes": notes,
        # Club and shared boats change skipper constantly; that isn't a new skipper of record.
        "shared": [r["boat"] for r in _rows("shared_boats.csv")],
        "events": events,
    }
    write_json(OUT, data)
    n_res = sum(len(e["results"]) for e in events)
    log.info(
        "%d events (%d merged duplicates removed), %d results, %d hulls -> %s (%.1f MB)",
        len(events),
        merged,
        n_res,
        len({r[0] for e in events for r in e["results"] if r[0]}),
        OUT.relative_to(ROOT),
        OUT.stat().st_size / 1e6,
    )
    return data
