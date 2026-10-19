"""Regatta Network: discovery (scan every results page for J/105) and a standings parser.

Pages are old table HTML. Each division is an ``<h2>`` holding ``<a name="<division>">`` and
"(N boats)", followed by a table whose columns are ``Pos | Sail | Boat | [Rating] | Skipper |
[Yacht Club] | race cells… | Total | Pos``. The markup nests ``<tr>`` inside ``<tr>``, so only a
row's own ``<td>`` children are read.

J/105s either have their own division or race in a mixed one (usually PHRF), flagged inline:
``[J105]`` after the skipper, ``9/J105`` as the sail, or ``J/105 Name`` as the boat. In a mixed
division only the flagged boats are kept and re-ranked among themselves (``mixed=True``).
Pages carry no city or state; the date comes from the year list (``MM/DD/YY`` prefix).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from j105.http import RAW, Fetcher, pmap, read_json, write_json
from j105.schema import TEST_EVENT, Event, Result

log = logging.getLogger(__name__)

SITE = "https://www.regattanetwork.com"
RESULTS = SITE + "/clubmgmt/applet_regatta_results.php"
FIRST_YEAR = 2006
J105 = re.compile(r"(?i)j\s*[/-]?\s*105\b")
J105_BYTES = re.compile(rb"(?i)j\s*[/-]?\s*105\b")
# A division name naming another class or a handicap system is mixed, e.g. "J/105 and J/88".
OTHER_CLASS = re.compile(r"(?i)\bj\s*[/-]?\s*(?!105\b)\d{2,3}\b|\bphrf\b|\borc\b|\bmixed\b")
INDEX = RAW / "rn_index.json"
CHECKED = RAW / "cache" / "regattanetwork" / "checked.json"
EVENTS = RAW / "rn_events.json"


def _fetcher() -> Fetcher:
    return Fetcher("regattanetwork")


def page_path(rid: str) -> str:
    return f"pages/{rid}.html"


# --- discovery ---------------------------------------------------------------------------------


def discover() -> list[dict[str, Any]]:
    """Scan every results page for a J/105 mention; keep the hits.

    Resumable: hits are cached as pages, and every checked id is recorded in ``checked.json``
    (misses from the current and previous year are rechecked, since results may be posted late).
    """
    f = _fetcher()
    this_year = dt.date.today().year
    events: dict[str, dict[str, Any]] = {}
    for y in range(FIRST_YEAR, this_year + 1):
        body = f.bytes(
            f"{SITE}/html/results.php",
            {"year": y},
            cache=f"years/{y}.html",
            refresh=y >= this_year - 1,
        )
        for ev in _year_list(body or b"", y):
            events.setdefault(ev["id"], ev)
        log.info("%d: %d events so far", y, len(events))
    checked: dict[str, bool] = read_json(CHECKED, {})

    def check(ev: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        rid = ev["id"]
        if (f.cache_dir / page_path(rid)).exists():
            return ev, True
        if rid in checked and (checked[rid] or ev["year"] < this_year - 1):
            return ev, checked[rid]
        body = f.bytes(RESULTS, {"regatta_id": rid})
        if body is None:
            return ev, False
        hit = bool(J105_BYTES.search(body))
        if hit:
            path = f.cache_dir / page_path(rid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        checked[rid] = hit
        return ev, hit

    hits = []
    for n, (ev, hit) in enumerate(pmap(check, list(events.values()), every=500), 1):
        if hit:
            hits.append(ev)
        if n % 500 == 0:
            write_json(CHECKED, checked)
    write_json(CHECKED, checked)
    write_json(INDEX, hits, indent=0)
    log.info("%d of %d results pages mention J/105", len(hits), len(events))
    return hits


def _year_list(body: bytes, year: int) -> list[dict[str, Any]]:
    out = []
    for row in re.findall(rb"<tr[^>]*>(.*?)</tr>", body, flags=re.S):
        ids = re.findall(rb"regatta_id=(\d+)", row)
        if not ids:
            continue
        s = BeautifulSoup(row, "html.parser").get_text(" ", strip=True)
        title = re.sub(
            r"\s+", " ", s.replace("[ Event Website ]", "").replace("[ View Results ]", "")
        )
        out.append({"id": ids[0].decode(), "year": year, "title": title.strip()})
    return out


# --- parsing -----------------------------------------------------------------------------------


def _text(x: Tag) -> str:
    return re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()


def _date(title: str) -> str:
    """ISO date from a year-list title such as ``05/20/06 Sea Lake Regatta …``."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\b", title)
    if not m:
        return ""
    mo, d, y = (int(g) for g in m.groups())
    try:
        return dt.date(y + 2000 if y < 100 else y, mo, d).isoformat()
    except ValueError:
        return ""


def _num(s: str) -> float | None:
    m = re.match(r"\s*\[?(-?\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def _clean_sail(s: str) -> tuple[str, str]:
    """``"USA 519"`` -> ``("519", "USA")``; ``"9/J105"`` -> ``("9", "")``."""
    s = J105.sub("", s).strip(" /-")
    if "/" in s:  # "Bow/ Sail" columns print "bow / sail"
        s = s.split("/")[-1].strip()
    m = re.match(r"([A-Za-z]{2,3})?\s*-?\s*(\S.*)$", s)
    if not m:
        return s, ""
    return m.group(2).strip(), (m.group(1) or "").upper()


def _clean_name(s: str) -> str:
    s = re.sub(r"\[[^\]]*\]", " ", s)  # inline tags such as [1B][J105]
    s = re.sub(r"(?i)^\s*j\s*[/-]?\s*105\b[\s:-]*", "", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def _column(header: list[str], *names: str) -> int | None:
    for i, h in enumerate(header):
        if any(n in h.lower() for n in names):
            return i
    return None


def parse_division(h2: Tag) -> dict[str, Any] | None:
    """Rows of the table that follows one division heading, or None if there is no table."""
    anchor = h2.find("a", attrs={"name": True})
    division = str(anchor["name"]).strip() if anchor else _text(h2).split("(")[0].strip()
    heading = _text(h2)
    size = re.search(r"\(\s*(\d+)\s*boats?\s*\)", heading)
    races = re.search(r"(\d+)\s+races?\s+scored", heading)
    table = h2.find_next("table")
    if table is None or table.find_previous("h2") is not h2:
        return None
    header: list[str] = []
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [_text(td) for td in tr.find_all(["td", "th"], recursive=False)]
        if not cells:
            continue
        if cells[0] == "Pos":
            header = [c.lower() for c in cells]
        elif header and len(cells) == len(header) and re.match(r"\d+", cells[0]):
            rows.append(cells)
    if not header:
        return None
    return {
        "division": division,
        "division_size": int(size.group(1)) if size else len(rows),
        "races": int(races.group(1)) if races else 0,
        "header": header,
        "rows": rows,
    }


def _result(div: dict[str, Any], cells: list[str]) -> Result:
    h = div["header"]
    sail_i, boat_i = _column(h, "sail"), _column(h, "boat")
    skip_i, club_i = _column(h, "skipper"), _column(h, "yacht club", "club")
    total_i = _column(h, "total")
    sail, country = _clean_sail(cells[sail_i]) if sail_i is not None else ("", "")
    return {
        "sail": sail,
        "sail_country": country,
        "boat": _clean_name(cells[boat_i]) if boat_i is not None else "",
        "skipper": _clean_name(cells[skip_i]) if skip_i is not None else "",
        "club": cells[club_i] if club_i is not None else "",
        "net": _num(cells[total_i]) if total_i is not None else None,
        "place": int(re.match(r"\d+", cells[0]).group()),  # type: ignore[union-attr]
    }


def _flagged(div: dict[str, Any], cells: list[str]) -> bool:
    h = div["header"]
    cols = [_column(h, "sail"), _column(h, "boat"), _column(h, "skipper")]
    return any(i is not None and J105.search(cells[i]) for i in cols)


def parse_page(html: bytes | str, meta: dict[str, Any]) -> list[Event]:
    """Every J/105 standings block on one results page, in the common event schema."""
    soup = BeautifulSoup(html, "html.parser")
    rid = str(meta["id"])
    title = _text(soup.title) if soup.title else ""
    name = re.sub(r"\s*-\s*Series Standing\s*$", "", title).strip()
    head = _text(soup.body).split("|")[0].strip() if soup.body else ""
    host = head[len(name) :].strip() if name and head.startswith(name) else ""
    date = _date(meta.get("title", ""))
    out: list[Event] = []
    for h2 in soup.find_all("h2"):
        div = parse_division(h2)
        if not div or not div["rows"]:
            continue
        own = bool(J105.search(div["division"]))
        mixed = not own or bool(OTHER_CLASS.search(div["division"]))
        rows = [c for c in div["rows"] if not mixed or _flagged(div, c)]
        if not rows:
            if own:
                log.warning("%s: mixed division %r has no flagged J/105s", rid, div["division"])
            continue
        results = [_result(div, c) for c in rows]
        if mixed:  # keep the division's order, re-ranked among J/105s only
            results.sort(key=lambda r: r["place"])
            for i, r in enumerate(results, 1):
                r["place"] = i
        ev: Event = {
            "source": "regattanetwork",
            "event_id": rid,
            "class_id": div["division"],
            "class": div["division"],
            "name": name or meta.get("title", ""),
            "start": date,
            "end": date,
            "city": "",
            "state": "",
            "country": "",
            "host": host,
            "url": f"{RESULTS}?regatta_id={rid}",
            "fleet": len(results),
            "races": div["races"],
            "scored": div["races"] > 0 and any(r["net"] for r in results),
            "results": results,
        }
        if mixed:
            ev["mixed"] = True
            ev["division_size"] = div["division_size"]
        out.append(ev)
    return out


def standings() -> list[Event]:
    """Parse every cached J/105 page listed in the index. Fetches any page not yet cached."""
    f = _fetcher()
    idx = [m for m in read_json(INDEX, []) if not TEST_EVENT.search(m["title"])]

    def one(meta: dict[str, Any]) -> list[Event]:
        body = f.bytes(RESULTS, {"regatta_id": meta["id"]}, cache=page_path(meta["id"]))
        return parse_page(body, meta) if body else []

    out: list[Event] = []
    empty = []
    for meta, evs in zip(idx, pmap(one, idx, every=100), strict=True):
        out += evs
        if not evs:
            empty.append(meta["id"])
    write_json(EVENTS, out)
    log.info(
        "%d J/105 blocks from %d pages (%d mixed); %d pages yielded none: %s",
        len(out),
        len(idx),
        sum(1 for e in out if e.get("mixed")),
        len(empty),
        " ".join(empty[:30]),
    )
    return out
