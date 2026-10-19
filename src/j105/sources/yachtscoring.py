"""Yacht Scoring (api.yachtscoring.com): discovery and standings.

Discovery scans every public event's ``/splits`` for a J/105 class; standings come from
``/cumulative-result`` (final order, net points) joined to ``/boats`` (club, home port, build
year, YS ``boatId``). Never store membership numbers, classifications or crew lists.

Each boat in ``cumulative-result`` has a ``design``. J/105s also race in PHRF, ORC and other
mixed classes, and some "J/105" classes are shared ("J/88 + J/105"). A class named only for
J/105 is one-design (a lone odd ``design`` is taken as an entry typo); any other class holding
J/105-design boats is a mixed block: only the J/105s are kept, in official order, re-ranked
among themselves (``mixed=True``, ``division_size`` = whole class). ``discover_designs()``
finds such classes in events whose splits name no J/105 class.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any

from j105.http import RAW, Fetcher, pmap, read_json, write_json
from j105.identity import sail_key
from j105.schema import Event, Result, is_recent

log = logging.getLogger(__name__)

API = "https://api.yachtscoring.com/v1/public/event"
J105 = re.compile(r"(?i)j\s*[/-]?\s*105(?!\d)")  # "J/105", "J 105", "J105s"
# A class name naming another class or a handicap system is mixed, e.g. "J/88 + J/105".
OTHER_CLASS = re.compile(
    r"(?i)\bj\s*[/-]?\s*(?!105(?!\d))\d{2,3}\b|\bphrf\b|\borc\b|\birc\b|\bmixed\b"
)
INDEX = RAW / "ys_index.json"
DESIGN_INDEX = RAW / "ys_design_index.json"
DESIGN_CHECKED = RAW / "cache" / "yachtscoring" / "design_checked.json"
EVENTS = RAW / "ys_events.json"
FIRST_YEAR = 2006
NORTH_AMERICA = {"", "usa", "us", "united states", "canada", "can", "ca", "bermuda", "ber"}


def _fetcher() -> Fetcher:
    return Fetcher("yachtscoring", {"Accept": "application/json"})


def discover() -> list[dict[str, Any]]:
    """Find every event with a J/105 split. Resumable: each ``/splits`` reply is cached."""
    f = _fetcher()
    events = _listing(f)

    def check(ev: dict[str, Any]) -> dict[str, Any] | None:
        recent = is_recent(ev.get("endDate") or ev.get("startDate") or "", days=60)
        d = f.json(f"{API}/{ev['id']}/splits", cache=f"splits/{ev['id']}.json", refresh=recent)
        classes = [
            {"id": r["id"], "name": r.get("splitClassName"), "num": r.get("splitClass")}
            for r in (d or {}).get("rows") or []
            if J105.search(str(r.get("splitClassName") or ""))
        ]
        if not classes:
            return None
        return {
            "id": ev["id"],
            "name": (ev.get("name") or "").strip(),
            "start": (ev.get("startDate") or "")[:10],
            "classes": classes,
        }

    out = [x for x in pmap(check, events, every=500) if x]
    write_json(INDEX, out, indent=0)
    log.info("%d events with a J/105 class; %d failed fetches", len(out), len(f.failures))
    return out


def _listing(f: Fetcher) -> list[dict[str, Any]]:
    """Every public event. Not cached: listing rows carry organizers' emails and phones."""
    events: list[dict[str, Any]] = []
    for page in range(100):
        d = f.json(API, {"size": 500, "page": page})
        rows = (d or {}).get("rows") or []
        if not rows:
            break
        keep = ("id", "name", "startDate", "endDate", "city", "state", "country")
        events += [{k: r.get(k) for k in keep} for r in rows]
    # Rows shift between pages while events are being added, so an id can be listed twice.
    events = list({e["id"]: e for e in events}.values())
    log.info("%d events listed", len(events))
    return events


def discover_designs() -> list[dict[str, Any]]:
    """Find J/105-design boats in events whose splits name no J/105 class (PHRF, ORC, ...).

    Scans ``cumulative-result`` of every North American event since 2006 not already in
    ``ys_index.json``. Resumable: each checked id is recorded in ``design_checked.json`` and
    hits are cached; events that ended in the last 60 days are rechecked.
    """
    f = _fetcher()
    indexed = {x["id"] for x in read_json(INDEX, [])}
    today = dt.date.today().isoformat()
    todo = [
        ev
        for ev in _listing(f)
        if ev["id"] not in indexed
        and str(FIRST_YEAR) <= (ev.get("startDate") or "")[:10] <= today
        and (ev.get("country") or "").strip().lower() in NORTH_AMERICA
    ]
    checked: dict[str, list[str]] = read_json(DESIGN_CHECKED, {})
    log.info("%d events to scan for J/105 designs, %d checked before", len(todo), len(checked))

    def check(ev: dict[str, Any]) -> list[str] | None:
        eid = str(ev["id"])
        if eid in checked and not is_recent(ev.get("endDate") or "", days=60):
            return checked[eid]
        body = f.bytes(f"{API}/{eid}/cumulative-result")
        if body is None:
            return None
        try:
            hits = [str(bl["className"]) for bl in _blocks(json.loads(body), []) if _kind(bl)]
        except json.JSONDecodeError:
            return None
        if hits:
            path = f.cache_dir / f"cumulative/{eid}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        checked[eid] = hits
        return hits

    out = []
    for n, (ev, hits) in enumerate(zip(todo, pmap(check, todo, every=250), strict=True), 1):
        if hits:
            start = (ev.get("startDate") or "")[:10]
            out.append({"id": ev["id"], "name": (ev.get("name") or "").strip(), "start": start,
                        "classes": [{"name": h} for h in hits]})  # fmt: skip
        if n % 250 == 0:
            write_json(DESIGN_CHECKED, checked)
    write_json(DESIGN_CHECKED, checked)
    write_json(DESIGN_INDEX, out, indent=0)
    log.info("%d events with J/105-design boats; %d failed fetches", len(out), len(f.failures))
    return out


def _is_j105(b: dict[str, Any]) -> bool:
    return bool(J105.search(str(b.get("design") or "")))


def _kind(bl: dict[str, Any]) -> str:
    """``"one-design"``, ``"mixed"`` (a class holding some J/105s) or ``""`` (no J/105s)."""
    name = str(bl.get("className") or "")
    boats = bl.get("boats") or []
    others = sum(1 for b in boats if str(b.get("design") or "").strip() and not _is_j105(b))
    if J105.search(name) and not OTHER_CLASS.search(name) and others < 2:
        return "one-design"
    # Every boat a J/105, e.g. "PHRF-3 J105": a J/105 fleet scored under a handicap name.
    if boats and all(_is_j105(b) for b in boats):
        return "one-design"
    return "mixed" if any(_is_j105(b) for b in boats) else ""


def _blocks(o: Any, out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every class block (a dict with ``className`` and ``boats``) anywhere in the reply."""
    if isinstance(o, dict):
        if "boats" in o and "className" in o:
            out.append(o)
        for v in o.values():
            _blocks(v, out)
    elif isinstance(o, list):
        for v in o:
            _blocks(v, out)
    return out


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _row(b: dict[str, Any], info: dict[str, Any], place: int) -> Result:
    o = info.get("owner") or b.get("owner") or {}
    recs = b.get("records") or []
    return {
        "sail": str(b.get("sailNumber") or "").strip(),
        "sail_country": (b.get("sailPrefix") or "").strip().upper(),
        "boat": (b.get("name") or "").strip(),
        "skipper": f"{o.get('firstName') or ''} {o.get('lastName') or ''}".strip(),
        "club": (o.get("club") or "").strip(),
        "home": ", ".join(z.strip() for z in (o.get("city"), o.get("state")) if z),
        "built": info.get("year"),
        "ys_boat": info.get("boatId"),
        "net": _num(b.get("raceTotal")),
        "races_sailed": sum(1 for r in recs if (r.get("finishStatus") or "") == "AOK"),
        "place": place,
    }


def standings_for(f: Fetcher, x: dict[str, Any]) -> list[Event]:
    eid = x["id"]
    refresh = is_recent(x.get("start") or "", days=35)
    ev = f.json(f"{API}/{eid}", cache=f"event/{eid}.json", refresh=refresh) or {}
    cr = f.json(f"{API}/{eid}/cumulative-result", cache=f"cumulative/{eid}.json", refresh=refresh)
    boats: list[dict[str, Any]] = []
    for page in range(50):
        d = f.json(
            f"{API}/{eid}/boats",
            {"size": 200, "page": page},
            cache=f"boats/{eid}-{page}.json",
            refresh=refresh,
        )
        rows = (d or {}).get("rows") or []
        boats += rows
        if not rows or len(boats) >= int((d or {}).get("count") or 0):
            break
    by_id = {str(b.get("id")): b for b in boats}
    hc = ev.get("hostClub") or {}
    out: list[Event] = []
    seen: set[tuple[str, str]] = set()
    blocks = []
    for bl in _blocks(cr or {}, []):
        cname = str(bl.get("className") or "")
        key = (str(bl.get("class")), cname)
        kind = _kind(bl)
        # Some replies repeat a class block (e.g. under two divisions); keep the first.
        if kind and key not in seen:
            seen.add(key)
            blocks.append((kind, bl))
    one_design = {
        sail_key(str(b.get("sailNumber") or ""))
        for kind, bl in blocks
        if kind == "one-design"
        for b in bl["boats"]
    }
    for kind, bl in blocks:
        mixed = kind == "mixed"
        boats = [b for b in bl.get("boats") or [] if not mixed or _is_j105(b)]
        # J/105s scored in their own class and again in a handicap class: count them once.
        if mixed and {sail_key(str(b.get("sailNumber") or "")) for b in boats} & one_design:
            if not {sail_key(str(b.get("sailNumber") or "")) for b in boats} <= one_design:
                log.info("skipped %s %r: some J/105s also in a J/105 class", eid, bl["className"])
            continue
        rows: list[Result] = []
        races: set[Any] = set()
        # Boats arrive in official finishing order (tiebreaks applied), so keep that order.
        for b in boats:
            recs = b.get("records") or []
            races |= {r.get("raceNumber") for r in recs}
            rows.append(_row(b, by_id.get(str(b.get("eventBoatId"))) or {}, len(rows) + 1))
        e: Event = {
            "source": "yachtscoring",
            "event_id": str(eid),
            "class_id": str(bl.get("class") or ""),
            "class": str(bl.get("className") or ""),
            "name": (ev.get("name") or x["name"]).strip(),
            "start": (ev.get("startDate") or x.get("start") or "")[:10],
            "end": (ev.get("endDate") or "")[:10],
            "city": (ev.get("city") or "").strip(),
            "state": (ev.get("state") or "").strip(),
            "country": (ev.get("country") or "").strip(),
            "region": (ev.get("eventRegion") or "").strip(),
            "host": (hc.get("name") or "").strip(),
            "url": f"https://www.yachtscoring.com/event_results_cumulative/{eid}",
            "fleet": len(rows),
            "races": len(races - {None}),
            "scored": any(r["net"] for r in rows),
            "results": rows,
        }
        if mixed:
            e["mixed"] = True
            e["division_size"] = len(bl.get("boats") or [])
        out.append(e)
    if not out:
        log.info("no J/105 block in cumulative results: %s %s", eid, x["name"][:60])
    return out


def standings() -> list[Event]:
    """Standings for every indexed event. Resumable: all replies are cached per event."""
    f = _fetcher()
    by_id = {x["id"]: x for x in read_json(DESIGN_INDEX, []) + read_json(INDEX, [])}
    idx = list(by_id.values())
    out: list[Event] = []
    for evs in pmap(lambda x: standings_for(f, x), idx, every=50):
        out += evs
    write_json(EVENTS, out)
    log.info(
        "%d class blocks (%d mixed) from %d events; %d network requests; %d failed",
        len(out),
        sum(1 for e in out if e.get("mixed")),
        len(idx),
        f.network_hits,
        len(f.failures),
    )
    return out
