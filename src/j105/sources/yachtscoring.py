"""Yacht Scoring (api.yachtscoring.com): discovery and standings.

Discovery scans every public event's ``/splits`` for a J/105 class; standings come from
``/cumulative-result`` (final order, net points) joined to ``/boats`` (club, home port, build
year, YS ``boatId``). Never store membership numbers, classifications or crew lists.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from j105.http import RAW, Fetcher, pmap, read_json, write_json
from j105.schema import Event, Result, is_recent

log = logging.getLogger(__name__)

API = "https://api.yachtscoring.com/v1/public/event"
J105 = re.compile(r"(?i)j\s*[/-]?\s*105\b")
INDEX = RAW / "ys_index.json"
EVENTS = RAW / "ys_events.json"


def _fetcher() -> Fetcher:
    return Fetcher("yachtscoring", {"Accept": "application/json"})


def discover() -> list[dict[str, Any]]:
    """Find every event with a J/105 split. Resumable: each ``/splits`` reply is cached."""
    f = _fetcher()
    events: list[dict[str, Any]] = []
    for page in range(100):
        d = f.json(API, {"size": 500, "page": page})
        rows = (d or {}).get("rows") or []
        if not rows:
            break
        events += rows
    log.info("%d events listed", len(events))

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
    for bl in _blocks(cr or {}, []):
        cname = str(bl.get("className") or "")
        key = (str(bl.get("class")), cname)
        # Some replies repeat a class block (e.g. under two divisions); keep the first.
        if not J105.search(cname) or key in seen:
            continue
        seen.add(key)
        rows: list[Result] = []
        races: set[Any] = set()
        # Boats arrive in official finishing order (tiebreaks applied), so keep that order.
        for b in bl.get("boats") or []:
            info = by_id.get(str(b.get("eventBoatId"))) or {}
            o = info.get("owner") or b.get("owner") or {}
            recs = b.get("records") or []
            races |= {r.get("raceNumber") for r in recs}
            rows.append(
                {
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
                    "place": len(rows) + 1,
                }
            )
        out.append(
            {
                "source": "yachtscoring",
                "event_id": str(eid),
                "class_id": str(bl.get("class") or ""),
                "class": cname,
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
        )
    if not out:
        log.info("no J/105 block in cumulative results: %s %s", eid, x["name"][:60])
    return out


def standings() -> list[Event]:
    """Standings for every indexed event. Resumable: all replies are cached per event."""
    f = _fetcher()
    idx = read_json(INDEX, [])
    out: list[Event] = []
    for evs in pmap(lambda x: standings_for(f, x), idx, every=50):
        out += evs
    write_json(EVENTS, out)
    log.info(
        "%d class blocks from %d events; %d network requests; %d failed",
        len(out),
        len(idx),
        f.network_hits,
        len(f.failures),
    )
    return out
