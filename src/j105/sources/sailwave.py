"""Sailwave HTML results pages (sailwave.com/results/... or a club's own site).

Sailwave publishes one page per series: ``<h1>`` event, ``<h2>`` venue, then per fleet an
``<h3 class="summarytitle">`` and a ``<table class="summarytable">`` with columns such as
``Rank | Boat Name | Boat Type/Class | SailNo | Helm/Skipper | Club | R1... | Total | Nett``.
Race titles (``<h3 class="racetitle">R1 - J 105 Fleet - June 20, 2022``) give the dates.

There is no index of J/105 pages: sailwave.com/results lists ~12,500 uploads from all over the
world, so pages come from the reviewed list ``data/sources/sailwave.csv`` (url, city, state,
host, note). A fleet named for J/105 is one-design unless two or more boats are another type;
in any other fleet the J/105s (by type) are re-ranked among themselves (``mixed=True``).

Terms: sailwave.com's robots.txt allows /results; no terms of use are posted. Raw pages stay in
the git-ignored cache; derived standings link back to the page.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import re
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup, Tag

from j105.http import RAW, ROOT, Fetcher, pmap, read_json, write_json
from j105.schema import Event, Result, race_cell

log = logging.getLogger(__name__)

J105 = re.compile(r"(?i)j\s*[/-]?\s*105(?!\d)")
PAGES = ROOT / "data" / "sources" / "sailwave.csv"
INDEX = RAW / "sailwave_index.json"
EVENTS = RAW / "sailwave_events.json"


def _fetcher() -> Fetcher:
    return Fetcher("sailwave", delay=2)


def _cache(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    return "pages/" + re.sub(r"[^\w.-]+", "_", u.netloc + urllib.parse.unquote(u.path))


def discover() -> list[dict[str, Any]]:
    """The reviewed page list, as the index."""
    with PAGES.open(newline="", encoding="utf-8") as fh:
        out = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
    write_json(INDEX, out, indent=0)
    log.info("%d Sailwave pages listed", len(out))
    return out


def _text(x: Tag) -> str:
    return re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()


def _num(s: str) -> float | None:
    m = re.match(r"\(?\s*(\d+(?:\.\d+)?)", s)
    return float(m[1]) if m else None


def _date(s: str) -> str:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def _pick(col: dict[str, int], *names: str) -> int | None:
    for n in names:
        if n in col:
            return col[n]
    return None


def parse_page(html: str, meta: dict[str, Any]) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = _text(h1) if h1 else meta["url"].rsplit("/", 1)[-1]
    out: list[Event] = []
    for title in soup.find_all("h3", class_="summarytitle"):
        fleet = _text(title)
        table = title.find_next("table")
        if not isinstance(table, Tag):
            continue
        trs = table.find_all("tr")
        header = [_text(c).lower() for c in trs[0].find_all(["th", "td"])] if trs else []
        col = {h: i for i, h in enumerate(header)}
        rows = [[_text(c) for c in tr.find_all("td")] for tr in trs[1:]]
        rows = [r for r in rows if len(r) >= len(header) and any(r)]
        typ = _pick(col, "boat type", "class", "type", "design")
        is_j = [bool(typ is not None and J105.search(r[typ])) for r in rows]
        others = sum(1 for r, j in zip(rows, is_j, strict=True) if not j and typ is not None
                     and r[typ])  # fmt: skip
        one_design = bool(J105.search(fleet)) and others < 2
        mixed = not one_design and any(is_j)
        if not (one_design or mixed):
            continue
        keep = [r for r, j in zip(rows, is_j, strict=True) if one_design or j]
        rank, net = _pick(col, "rank", "pos", "place"), _pick(col, "nett", "net", "total")
        sail, boat = _pick(col, "sailno", "sail no", "sail"), _pick(col, "boat name", "boat")
        helm, club = _pick(col, "helm", "skipper", "owner"), _pick(col, "club")
        official = [_num(r[rank]) if rank is not None else None for r in keep]
        results: list[Result] = []
        for i, (r, p) in enumerate(zip(keep, official, strict=True)):
            place = i + 1
            if p is not None:  # re-rank among J/105s; equal official ranks stay tied
                place = 1 + sum(1 for q in official if q is not None and q < p)
            raw_sail = r[sail] if sail is not None else ""
            country = re.match(r"\s*([A-Za-z]{3})\s+\d", raw_sail)
            results.append(
                {
                    "sail": re.sub(r"^[A-Za-z]{3}\s+", "", raw_sail).strip(),
                    "sail_country": country[1].upper() if country else "",
                    "boat": r[boat] if boat is not None else "",
                    "skipper": r[helm] if helm is not None else "",
                    "club": r[club] if club is not None else "",
                    "net": _num(r[net]) if net is not None else None,
                    "race_scores": [
                        race_cell(r[i]) for i, h in enumerate(header) if re.fullmatch(r"r\d+", h)
                    ],
                    "place": place,
                }
            )
        races = [h for h in header if re.fullmatch(r"r\d+", h)]
        dates = sorted(
            d
            for h in soup.find_all("h3", class_="racetitle")
            if fleet in _text(h) and (d := _date(_text(h).rsplit(" - ", 1)[-1]))
        )
        e: Event = {
            "source": "sailwave",
            "event_id": meta["url"].split("://", 1)[-1],
            "class_id": fleet,
            "class": fleet,
            "name": name,
            "start": dates[0] if dates else meta.get("start", ""),
            "end": dates[-1] if dates else meta.get("start", ""),
            "city": meta.get("city", ""),
            "state": meta.get("state", ""),
            "country": meta.get("country", "") or "USA",
            "host": meta.get("host", ""),
            "url": meta["url"],
            "fleet": len(results),
            "races": len(races),
            "scored": bool(races) and any(x["net"] for x in results),
            "results": results,
        }
        if mixed:
            e["mixed"] = True
            e["division_size"] = len(rows)
        out.append(e)
    return out


def standings() -> list[Event]:
    f = _fetcher()

    def one(meta: dict[str, Any]) -> list[Event]:
        body = f.bytes(urllib.parse.quote(meta["url"], safe=":/?=&%"), cache=_cache(meta["url"]))
        return parse_page(body.decode("utf-8", "replace"), meta) if body else []

    idx = read_json(INDEX, [])
    out: list[Event] = []
    for evs in pmap(one, idx, every=20):
        out += evs
    write_json(EVENTS, out)
    log.info("%d J/105 blocks (%d mixed) from %d pages; %d failed", len(out),
             sum(1 for e in out if e.get("mixed")), len(idx), len(f.failures))  # fmt: skip
    return out
