"""Clubspot (Parse backend + results service): discovery and standings.

Clubspot exposes no place field: rank by ``net`` then ``total``. Tiebreaks are not exposed,
so tied boats can come out in the wrong order. Skip test and "CLONED" regattas.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from j105.http import RAW, Fetcher, pmap, read_json, write_json
from j105.schema import Event, Result, is_recent, rank

log = logging.getLogger(__name__)

PARSE = "https://theclubspot.com/parse/classes"
RESULTS = "https://results.theclubspot.com/clubspot-results-v4"
J105_REGEX = r"(?i)j\s*/?\s*-?\s*105"
SKIP = re.compile(r"(?i)\btest\b|cloned")
PHONE = re.compile(r"\s*\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")
INDEX = RAW / "clubspot_index.json"
EVENTS = RAW / "clubspot_events.json"


def _fetcher() -> Fetcher:
    return Fetcher("clubspot", {"X-Parse-Application-Id": "myclubspot2017"})


def discover() -> list[dict[str, Any]]:
    """Every Clubspot boat class whose name looks like J/105, with its regatta."""
    f = _fetcher()
    classes: list[dict[str, Any]] = []
    while True:
        params = {
            "where": json.dumps({"name": {"$regex": J105_REGEX}}),
            "keys": "name,regattaObject",
            "limit": 1000,
            "skip": len(classes),
        }
        rows = (f.json(f"{PARSE}/boatClasses", params) or {}).get("results") or []
        classes += rows
        if len(rows) < 1000:
            break
    ids = sorted({c["regattaObject"]["objectId"] for c in classes if c.get("regattaObject")})
    info: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 100):
        params = {
            "where": json.dumps({"objectId": {"$in": ids[i : i + 100]}}),
            "keys": "name,startDate,endDate,clubObject",
            "limit": 100,
        }
        for g in (f.json(f"{PARSE}/regattas", params) or {}).get("results") or []:
            info[g["objectId"]] = g
    out = []
    for c in classes:
        g = info.get((c.get("regattaObject") or {}).get("objectId", ""))
        if not g:
            continue
        out.append(
            {
                "regatta": g["objectId"],
                "class_id": c["objectId"],
                "class": c["name"],
                "name": (g.get("name") or "").strip(),
                "start": ((g.get("startDate") or {}).get("iso") or "")[:10],
                "club": (g.get("clubObject") or {}).get("objectId"),
            }
        )
    write_json(INDEX, out, indent=0)
    log.info("%d J/105 classes in %d regattas", len(classes), len(ids))
    return out


def standings_for(f: Fetcher, x: dict[str, Any]) -> Event:
    rid, cid = x["regatta"], x["class_id"]
    refresh = is_recent(x.get("start") or "", days=35)
    g = f.json(f"{PARSE}/regattas/{rid}", cache=f"regatta/{rid}.json", refresh=refresh) or {}
    d = (
        f.json(
            f"{RESULTS}/{rid}",
            {"boatClassIDs": cid},
            cache=f"results/{rid}-{cid}.json",
            refresh=refresh,
        )
        or {}
    )
    regs = d.get("scoresByRegistration") or []
    rows: list[Result] = []
    for s in regs:
        ro = s.get("registrationObject") or {}
        r: Result = {
            "sail": str(ro.get("sailNumber") or "").strip(),
            "sail_country": (ro.get("sailNumber_country") or "").strip().upper(),
            "boat": (ro.get("boatName") or "").strip(),
            "skipper": f"{ro.get('firstName') or ''} {ro.get('lastName') or ''}".strip(),
            "club": (ro.get("clubName") or "").strip(),
            "net": float(s.get("net") or 0),
            "total": float(s.get("total") or 0),
            "place": 0,
        }
        if r["sail"] or r["boat"]:
            rows.append(r)
    rows = rank(rows)
    club_id = (g.get("clubObject") or {}).get("objectId")
    club = f.json(f"{PARSE}/clubs/{club_id}", cache=f"club/{club_id}.json") if club_id else None
    return {
        "source": "clubspot",
        "event_id": rid,
        "class_id": cid,
        "class": x["class"],
        "name": (g.get("name") or x["name"]).strip(),
        "start": ((g.get("startDate") or {}).get("iso") or "")[:10],
        "end": ((g.get("endDate") or {}).get("iso") or "")[:10],
        "city": (g.get("city") or "").strip(),
        "state": (g.get("state") or "").strip(),
        "country": (g.get("country") or "").strip(),
        "location": PHONE.sub("", g.get("location") or "").strip(),  # venue, no phone numbers
        "host": ((club or {}).get("name") or "").strip(),
        "url": f"https://www.theclubspot.com/regatta/{rid}/results",
        "fleet": len(rows),
        "races": len({z.get("race_number") for s in regs for z in s.get("scoring_data") or []}),
        "scored": any(r["net"] for r in rows),
        "results": rows,
    }


def standings() -> list[Event]:
    f = _fetcher()
    seen: set[tuple[str, str]] = set()
    todo = []
    for x in read_json(INDEX, []):
        key = (x["regatta"], x["class_id"])
        if SKIP.search(x["name"]) or key in seen:
            continue
        seen.add(key)
        todo.append(x)
    out = list(pmap(lambda x: standings_for(f, x), todo, every=50))
    write_json(EVENTS, out)
    log.info(
        "%d classes; %d network requests; %d failed", len(out), f.network_hits, len(f.failures)
    )
    return out
