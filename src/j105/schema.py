"""The common event schema every collector writes to ``data/raw/<source>_events.json``."""

from __future__ import annotations

import datetime as dt
import re
from typing import NotRequired, TypedDict

# Scorers' practice and copied events, e.g. RN "Test Rosenblum" (skippers "Kim Kardashian" ...).
TEST_EVENT = re.compile(r"(?i)\btest\b|cloned")


class Result(TypedDict):
    sail: str
    sail_country: str
    boat: str
    skipper: str
    club: str
    net: float | None
    place: int
    total: NotRequired[float | None]
    home: NotRequired[str]
    built: NotRequired[int | None]
    ys_boat: NotRequired[int | None]
    races_sailed: NotRequired[int]


# Functional form because the JSON key ``class`` is a Python keyword.
Event = TypedDict(
    "Event",
    {
        "source": str,
        "event_id": str,
        "class_id": str,
        # Division name as printed, e.g. "J/105", or "PHRF A" when J/105s raced in a mixed class.
        "class": str,
        "name": str,
        "start": str,
        "end": str,
        "city": str,
        "state": str,
        "country": str,
        "host": str,
        "url": str,  # official results page; always link back to it
        "fleet": int,  # J/105s ranked in ``results``
        "races": int,
        "scored": bool,
        "results": list[Result],
        "region": NotRequired[str],
        "location": NotRequired[str],
        # True when J/105s raced in a mixed division and were re-ranked among J/105s only.
        "mixed": NotRequired[bool],
        # Boats in the whole division when ``mixed``; ``fleet`` counts only the J/105s.
        "division_size": NotRequired[int],
    },
)


def is_recent(end: str, days: int = 21) -> bool:
    """True if an event ended within ``days`` (or has no usable date): its results may change."""
    try:
        d = dt.date.fromisoformat(end[:10])
    except ValueError:
        return True
    return d >= dt.date.today() - dt.timedelta(days=days)


def rank(results: list[Result], key: str = "net") -> list[Result]:
    """Sort by ``key`` (missing values last, stable) and assign places 1..n."""
    out = sorted(
        results,
        key=lambda r: (r.get(key) is None, r.get(key) or 0.0, r.get("total") or 0.0),  # type: ignore[operator]
    )
    for i, r in enumerate(out, 1):
        r["place"] = i
    return out
