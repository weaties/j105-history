"""State/province normalisation and the region each one belongs to.

Regions are broad sailing areas used for filters and participation charts. J/105 class fleet
numbers (e.g. Fleet 1 = San Francisco) go in ``data/identity/fleets.csv`` once confirmed.
"""

from __future__ import annotations

import re
from functools import cache
from typing import Any

NAMES = {
    "alabama": "AL", "california": "CA", "connecticut": "CT", "delaware": "DE", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "illinois": "IL", "indiana": "IN", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "new hampshire": "NH", "hampshire": "NH", "new jersey": "NJ", "new york": "NY",
    "north carolina": "NC", "ohio": "OH", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "texas": "TX", "virginia": "VA",
    "washington": "WA", "wisconsin": "WI", "british columbia": "BC", "nova scotia": "NS",
    "ontario": "ON", "quebec": "QC", "bermuda": "BM",
}  # fmt: skip

REGIONS = {
    "Pacific Northwest": {"WA", "OR", "BC"},
    "California": {"CA", "HI"},
    "Gulf & Texas": {"TX", "LA", "AL"},
    "Great Lakes": {"IL", "IN", "MI", "MN", "OH", "WI", "ON", "PA"},
    "New England": {"MA", "ME", "NH", "RI"},
    "Long Island Sound & NY/NJ": {"CT", "NY", "NJ"},
    "Chesapeake": {"MD", "VA", "DE"},
    "Southeast": {"NC", "SC", "GA", "FL"},
    "Atlantic Canada & Quebec": {"NS", "QC"},
    "Bermuda": {"BM"},
}
_BY_STATE = {s: r for r, states in REGIONS.items() for s in states}


def state_code(state: str) -> str:
    """``"Illinois"`` -> ``"IL"``; ``"NY NJ"`` -> ``"NY"``; unknown text is returned upper-cased."""
    s = re.sub(r"\s+", " ", state).strip().strip(".")
    if not s:
        return ""
    if s.lower() in NAMES:
        return NAMES[s.lower()]
    first = s.split()[0].upper()
    return first if len(first) == 2 else s.upper()


def region(state: str) -> str:
    return _BY_STATE.get(state_code(state), "")


# ``data/identity/host_clubs.csv`` statuses that are applied. ``proposed`` rows wait for review.
APPLIED = {"source", "printed", "confirmed"}


def host_key(host: str) -> str:
    """``"Hosted by The Houston Yacht Club"`` -> ``"houston yacht club"``."""
    h = re.sub(r"[^a-z0-9 ]", " ", host.lower())
    h = re.sub(r"\s+", " ", h).strip()
    return re.sub(r"^(hosted by )?(the )?", "", h)


@cache
def host_table() -> tuple[dict[str, str], dict[str, str]]:
    """Reviewed host -> state rows, as ``(by host key, by "source:event_id")``."""
    from j105.identity import _rows

    by_host: dict[str, str] = {}
    by_event: dict[str, str] = {}
    for r in _rows("host_clubs.csv"):
        if r["status"] not in APPLIED:
            continue
        if r["event"]:
            by_event[r["event"]] = r["state"]
        else:
            by_host[host_key(r["host"])] = r["state"]
    return by_host, by_event


def event_state(e: dict[str, Any]) -> str:
    """The event's state code: as the source printed it, else from the reviewed host table."""
    if e.get("state"):
        return state_code(e["state"])
    by_host, by_event = host_table()
    return by_event.get(f"{e['source']}:{e['event_id']}") or by_host.get(
        host_key(e.get("host") or ""), ""
    )
