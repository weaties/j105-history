"""Sloop Tavern Yacht Club (Seattle): race and series results from race.styc.org.

Discovery: the club's race pages (menu items between "Races" and "Race Info" on
www.styc.org) each embed ``racedata.js?mode=results_breaks_list&wa_race_abbr=<abbr>``, a script
that links every year's results (``race_info/<Race>/<year>/series.htm`` or ``race1.htm``).
Pages are PHRF/ORC results: one table per class, headed ``<h3>Class 1 - ...`` (series) or
``Class: 1 - ... - Start: ...`` (race), with columns ``Boat Name | SailNo | Boat Type | Skipper |
Rating | Club | race cells... | Total | Place`` (series) or start/finish/corrected times and
``Place`` (race). J/105s are found by ``Boat Type``. A class where every boat is a J/105 is
one-design; otherwise the J/105s are re-ranked among themselves (``mixed=True``,
``division_size`` = whole class), ties kept. For a single race, ``net`` is the class place.

Terms: www.styc.org's robots.txt asks for a 10 s crawl delay (race.styc.org has none); the
fetcher keeps one request per 10 s. No terms of use are posted. Raw pages stay in the
git-ignored cache; derived standings link back to the official page.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup, Tag

from j105.http import RAW, Fetcher, pmap, read_json, write_json
from j105.schema import Event, Result, race_cell

log = logging.getLogger(__name__)

SITE = "https://www.styc.org"
RACE = "https://race.styc.org"
J105 = re.compile(r"(?i)j\s*[/-]?\s*105(?!\d)")
CLASS = re.compile(r"Class:?\s*(\d+)\s*(?:-\s*([^-]+?))?\s*(?:-\s*Start|$)")
INDEX = RAW / "styc_index.json"
EVENTS = RAW / "styc_events.json"


def _fetcher() -> Fetcher:
    return Fetcher("styc", delay=10)


def _cache(url: str) -> str:
    """``https://race.styc.org/race_info/Fall Regatta/2025/race1.htm`` -> a cache path."""
    u = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(u.path).replace(" ", "_")
    if path.startswith("/race_info/"):
        return "pages/" + path.removeprefix("/race_info/")
    if u.query:  # racedata.js?mode=...&wa_race_abbr=<abbr>
        return "js/" + re.sub(r"\W+", "_", u.query) + ".js"
    return "site/" + (path.strip("/") or "index") + ".html"


def _get(f: Fetcher, url: str, refresh: bool = False) -> str:
    body = f.bytes(urllib.parse.quote(url, safe=":/?=&"), cache=_cache(url), refresh=refresh)
    return (body or b"").decode("latin-1")


def discover() -> list[dict[str, Any]]:
    """List every year's results page for every STYC race. Resumable: pages are cached."""
    f = _fetcher()
    menu = BeautifulSoup(_get(f, f"{SITE}/", refresh=True), "html.parser")
    races, on = [], False
    for a in menu.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label == "Races":
            on = True
        elif label == "Race Info":
            break
        elif on and a["href"].startswith(SITE) and a["href"] not in [r[1] for r in races]:
            races.append((label, a["href"]))
    log.info("%d STYC races", len(races))
    out = []
    for label, url in races:
        abbr = re.search(r"wa_race_abbr=(\w+)", _get(f, url))
        if not abbr:
            log.warning("no results list on %s", url)
            continue
        js = _get(f, f"{RACE}/cgi-bin/racedata.js?mode=results_breaks_list&wa_race_abbr={abbr[1]}",
                  refresh=True)  # fmt: skip
        for href in re.findall(r'href=\\"(https://race\.styc\.org/race_info/[^"\\?]+)', js):
            year = re.search(r"/(\d{4})/", href)
            out.append({"race": label, "year": int(year[1]) if year else 0, "url": href})
    write_json(INDEX, out, indent=0)
    log.info("%d results pages listed", len(out))
    return out


def _text(x: Tag) -> str:
    return re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()


def _num(s: str) -> float | None:
    m = re.match(r"\(?\s*(\d+(?:\.\d+)?)", s)
    return float(m[1]) if m else None


def _date(s: str) -> str:
    try:
        return dt.datetime.strptime(s.strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        return ""


def _title(soup: BeautifulSoup) -> tuple[str, str]:
    """Event name and date (``""`` on series pages, which carry no date)."""
    t = soup.find(class_="racetitle") or soup.find("h1")
    d = soup.find(class_="racedate")
    return (_text(t) if t else ""), (_date(_text(d)) if d else "")


def _class_label(table: Tag) -> tuple[str, str]:
    for s in table.find_all_previous(string=CLASS):
        m = CLASS.search(s)
        if m:
            return m[1], f"Class {m[1]}" + (f" - {m[2].strip()}" if m[2] else "")
    return "", ""


def parse_page(html: str, meta: dict[str, Any]) -> list[Event]:
    """J/105 blocks (one per class holding J/105s) from one STYC results page."""
    soup = BeautifulSoup(html, "html.parser")
    name, date = _title(soup)
    out: list[Event] = []
    for table in soup.find_all("table"):
        header = [_text(th) for th in table.find_all("th")]
        if "Boat Name" not in header or "Place" not in header:
            continue
        col = {h: i for i, h in enumerate(header)}
        rows = []
        for tr in table.find_all("tr"):
            cells = [_text(td) for td in tr.find_all("td", recursive=False)]
            if len(cells) >= len(header) and cells[col["Boat Name"]]:
                rows.append(cells)
        j105 = [c for c in rows if J105.search(c[col.get("Boat Type", 0)])]
        if not j105:
            continue
        races = sum(1 for h in header if re.fullmatch(r"Race \d+", h)) or 1
        net_col = col.get("Total", col["Place"])
        places = [_num(c[col["Place"]]) for c in j105]
        results: list[Result] = []
        for c, p in zip(j105, places, strict=True):
            # Re-rank among J/105s; boats on the same official place stay tied.
            place = 1 + sum(1 for q in places if q is not None and p is not None and q < p)
            sail = c[col["SailNo"]] if "SailNo" in col else ""
            results.append(
                {
                    "sail": re.sub(r"\s*\(.*", "", sail).strip(),
                    "sail_country": "",
                    "boat": c[col["Boat Name"]],
                    "skipper": c[col["Skipper"]] if "Skipper" in col else "",
                    "club": c[col["Club"]] if "Club" in col else "",
                    "net": _num(c[net_col]),
                    "race_scores": _race_scores(c, header, col),
                    "place": place if p is not None else len(j105),
                }
            )
        results.sort(key=lambda r: r["place"])
        class_id, label = _class_label(table)
        # A race page counts as sailed only if some boat in the class has a finish time.
        fin = col.get("Finish")
        if fin is None:
            finished = any(_num(c[net_col]) for c in rows)
        else:
            finished = any(re.match(r"\d+:\d", c[fin]) for c in rows)
        e: Event = {
            "source": "styc",
            "event_id": meta["url"].removeprefix(f"{RACE}/race_info/").removesuffix(".htm"),
            "class_id": class_id,
            "class": label,
            "name": name or f"{meta['year']} {meta['race']}",
            "start": meta.get("start") or date,
            "end": meta.get("end") or date,
            "city": "Seattle",
            "state": "WA",
            "country": "USA",
            "host": "Sloop Tavern Yacht Club",
            "url": meta["url"],
            "fleet": len(results),
            "races": races,
            "scored": finished,
            "results": results,
        }
        if len(j105) < len(rows):
            e["mixed"] = True
            e["division_size"] = len(rows)
        out.append(e)
    return out


def _race_scores(c: list[str], header: list[str], col: dict[str, int]) -> list[list[Any]]:
    """Series pages: the "Race n" cells. A race page: the class place, with a finish code."""
    cells = [race_cell(c[i]) for i, h in enumerate(header) if re.fullmatch(r"Race \d+", h)]
    if cells or "Total" in col:
        return cells
    sc = race_cell(c[col["Place"]])
    fin = c[col["Finish"]] if "Finish" in col else ""
    if re.fullmatch(r"[A-Z]{2,5}", fin):
        sc[1] = fin
    return [sc]


def _series_dates(f: Fetcher, url: str, html: str, refresh: bool) -> tuple[str, str]:
    """A series page has no date: read it from its first and last race pages."""
    links = re.findall(r"href=(race\d+)\.htm", html)
    if not links:
        return "", ""
    base = url.rsplit("/", 1)[0]
    first = _title(BeautifulSoup(_get(f, f"{base}/{links[0]}.htm", refresh), "html.parser"))[1]
    last = _title(BeautifulSoup(_get(f, f"{base}/{links[-1]}.htm", refresh), "html.parser"))[1]
    return first, last or first


def standings() -> list[Event]:
    """Parse every listed page; series pages holding J/105s also fetch race pages for dates."""
    f = _fetcher()
    this_year = dt.date.today().year

    def one(meta: dict[str, Any]) -> list[Event]:
        refresh = meta["year"] >= this_year  # this season's pages still change
        html = _get(f, meta["url"], refresh)
        if not J105.search(html):
            return []
        if meta["url"].endswith("/series.htm"):
            meta = {**meta}
            meta["start"], meta["end"] = _series_dates(f, meta["url"], html, refresh)
        return parse_page(html, meta)

    idx = read_json(INDEX, [])
    out: list[Event] = []
    for evs in pmap(one, idx, every=20):
        out += evs
    write_json(EVENTS, out)
    log.info(
        "%d J/105 blocks (%d mixed) from %d pages; %d network requests; %d failed",
        len(out),
        sum(1 for e in out if e.get("mixed")),
        len(idx),
        f.network_hits,
        len(f.failures),
    )
    return out
