"""J/105 Class Association results archive (archive.j105.org), 1996–2008.

One hand-made page per year, ``j105results<year>.html``: ``<h2>``/``<h3>`` event headings
("Galveston NOOD <br> September 24-26, 2004", "1996 North Americans (September 20-22),
Annapolis, MD"), each followed by results as ``<pre>`` text, ``<br>``-separated lines or
``<table>`` rows, often in the scorer's own layout (sail numbers missing, "Last,First"
skippers, throwouts in parentheses, totals before or after the race columns, home port on a
second line). The parser maps header rows to columns where it can and otherwise reads a row
as ``place … names/sail … scores``. Blocks it cannot read are logged with year and heading.

Terms: the archive is the class association's own site; robots.txt allows these pages and
there is no terms-of-use page. Raw pages stay in the git-ignored cache; only derived standings
are published, with attribution and a link to the year page (``#anchor`` when the page has one
next to the event). Results without a printed sail number keep ``sail=""``: they are resolved
by boat name in the identity pass, never invented here.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from j105.http import RAW, Fetcher, read_json, write_json
from j105.regions import NAMES, state_code
from j105.schema import Event, Result, race_cell

log = logging.getLogger(__name__)

SITE = "https://archive.j105.org"
YEARS = range(1996, 2009)
INDEX = RAW / "j105org_index.json"
EVENTS = RAW / "j105org_events.json"

J105 = re.compile(r"(?i)j\s*[/-]?\s*105(?!\d)")
OTHER_CLASS = re.compile(
    r"(?i)^\s*(class\s*\w*\s*[-:]?\s*)?(j\s*[/-]?\s*(?!105(?!\d))\d{2,3}\b|phrf|etchells|melges|farr|mumm|swan|sonar|shields|ido|irc|ims)"
)
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}  # noqa: SIM905
MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
# Places named in event headings ("Annapolis NOOD") -> state. Only unambiguous venue names.
VENUES = {
    "annapolis": "MD", "galveston": "TX", "larchmont": "NY", "san francisco": "CA",
    "marblehead": "MA", "chicago": "IL", "detroit": "MI", "san diego": "CA", "st. pete": "FL",
    "st pete": "FL", "key west": "FL", "charleston": "SC", "block island": "RI",
    "newport beach": "CA", "long beach": "CA", "toronto": "ON", "seattle": "WA",
    "miami": "FL", "texas": "TX", "marina del rey": "CA", "lake texoma": "TX",
    "big boat": "CA", "stfyc": "CA", "st. francis": "CA", "manhasset": "NY",
}  # fmt: skip
ABROAD = {
    "bacardi": "BER", "bermuda": "BER", "malta": "MLT", "mediterranean": "MLT",
    "cowes": "GBR", "united kingdom": "GBR", "uk nationals": "GBR", "chile": "CHI",
}  # fmt: skip
CANADA = {"ON", "QC", "NS", "BC", "NB", "PE", "NL", "MB", "SK", "AB"}

CODES = (
    r"(dnf|dnc|dns|dsq|ocs|raf|ret|bfd|zfp|scp|dpi|tle|rdg|dgm|ufd|nsc|dne|abs|ret|ret\.|p\d+|dnq)"
)
SCORE_TOKEN = re.compile(
    rf"(?i)^([\(\[\*-]?-?\s*\d+(\.\d+)?\*?([a-z]+\d*)?[\)\]]?(/\s*({CODES}|\d+%?|\d+(\.\d+)?))?\*?|{CODES}(/\d+(\.\d+)?)?|"
    rf"\(\s*{CODES}\s*\)|/\d+(\.\d+)?|--?|=|;|\.)$"
)
NUMBER = re.compile(r"-?\d+(\.\d+)?")
PLACE = re.compile(r"(?i)^(t-?)?(\d{1,3})(st|nd|rd|th|t)?[.)]?$")
SAIL = re.compile(r"(?i)^(#\s*|(usa|us|can|gbr|ksa|ber)\s*-?\s*)?(\d{1,6})$|^\?\?\?$")
HOME = re.compile(r",\s*[A-Za-z]{2}\b|,\s*(" + "|".join(NAMES) + r")\b", re.I)
CLUB = re.compile(
    r"(?i)\b(y\.?\s?c\.?|yacht club|sailing club|s\.?s\.?|squadron|ycc|nyyc|stfyc|sfyc)$"
    r"|^[A-Z]{2,6}YC$|yacht|club"
)
PERSONISH = re.compile(r"(?i)^[a-z]\.\s|\w+,\s?\w+|/|&| and |^[A-Z][a-z]+ [A-Z][a-z'-]+$")

ROLES = [
    ("place", r"pl|place|pos\.?|position|rank|overall place|no\.?|fin|final place"),
    ("sail", r"sail|sail ?#|sail ?no\.?|sail ?number|sailno|hull|hull ?#|hull ?no\.?|hull ?number|"
     r"hull nmbr|bow/sail|sail#|nmbr|\|sail no|sail no\.?"),
    # A bare "#" column is a sail number at some events and a bow number at others (Key West,
    # Miami, Charleston): resolved per block by resolve_bow_numbers().
    ("hash", r"#"),
    ("bow", r"bow ?#?|bow no\.?"),
    ("boat", r"boat|boat ?name|yacht|yacht ?name|boatname|yacht name|name"),
    ("skipper", r"skipper.*|owner.*|helm.*|entrant.*|skipper name"),
    ("home", r"home.*|from|city|port|state|address"),
    ("club", r"club|yacht club"),
    ("total", r"total.*|tot\.?|points|pts\.?|t|net|nett|final|score|total score"),
    ("class", r"fleet|class|boat ?type"),
]  # fmt: skip
RACE = re.compile(r"(?i)^(r(ace)?\s*-?\s*#?\s*\d+.*|#\s*\d+|\d{1,2})$")


def _fetcher() -> Fetcher:
    return Fetcher("j105org")


def page_url(year: int) -> str:
    return f"{SITE}/j105results{year}.html"


def discover() -> list[dict[str, Any]]:
    """List the yearly pages. The archive is static, so cached pages are never refetched.

    Fleet sub-pages linked from a year page (``fleet2/`` …) are recorded as leads, not crawled.
    """
    f = _fetcher()
    out = []
    for y in YEARS:
        body = f.bytes(page_url(y), cache=f"results/{y}.html")
        if not body:
            continue
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        leads = sorted(
            {
                a["href"]
                for a in soup.find_all("a", href=True)
                if re.match(r"(?i)^(\./)?fleet\d+/?", a["href"])
            }
        )
        out.append({"year": y, "url": page_url(y), "title": title, "fleet_pages": leads})
        if leads:
            log.info("%d: fleet sub-pages (not crawled): %s", y, " ".join(leads))
    write_json(INDEX, out, indent=1)
    return out


# --- page -> stream of headings, table rows and text lines ---------------------------------


def stream(html: bytes | str) -> list[tuple[str, Any]]:
    """``("h", text, anchor)``, ``("r", cells)`` for table rows, ``("t", line, in_pre)``."""
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    out: list[tuple[str, Any]] = []
    cur: list[str] = []
    anchor = [""]
    pre_flag = [False]

    def flush() -> None:
        if cur:
            for line in "".join(cur).split("\n"):
                if line.strip():
                    out.append(("t", line.rstrip(), pre_flag[0]))
            cur.clear()

    def walk(n: Tag, pre: bool) -> None:
        for c in n.children:
            if isinstance(c, NavigableString):
                s = str(c).replace("\xa0", " ")
                cur.append(s if pre else re.sub(r"\s+", " ", s))
            elif isinstance(c, Tag):
                nm = c.name.lower()
                if nm == "a" and c.get("name"):
                    anchor[0] = str(c["name"])
                if nm in ("h1", "h2", "h3", "h4"):
                    flush()
                    for a in c.find_all("a"):
                        if a.get("name"):
                            anchor[0] = str(a["name"])
                    text = re.sub(r"\s+", " ", c.get_text(" ").replace("\xa0", " ")).strip()
                    out.append(("h", text, anchor[0]))
                    anchor[0] = ""
                    continue
                if nm == "tr":
                    flush()
                    cells = [
                        re.sub(r"\s+", " ", td.get_text(" ").replace("\xa0", " ")).strip()
                        for td in c.find_all(["td", "th"], recursive=False)
                    ]
                    out.append(("r", cells))
                    continue
                if nm == "pre":
                    flush()
                    pre_flag[0] = True
                    walk(c, True)
                    flush()
                    pre_flag[0] = False
                    continue
                if nm in ("br", "p", "div", "li", "table", "hr", "tr", "ul"):
                    flush()
                walk(c, pre)
                if nm in ("p", "div", "li", "table", "ul"):
                    flush()

    walk(soup, False)
    flush()
    return out


# --- headings ----------------------------------------------------------------------------


def parse_date(text: str, year: int) -> tuple[str, str]:
    """``("2004-09-24", "2004-09-26")`` from "September 24-26, 2004"; month-only -> "2004-09"."""
    t = text.lower()
    ym = re.search(r"\b(19|20)\d{2}\b", t)
    y = int(ym.group(0)) if ym else year
    m = re.search(
        MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:-|&|,|to|and)\s*(?:" + MONTH +
        r"\s+)?(\d{1,2})(?!\d))?(?:\s*,?\s*\d{1,2})*",
        t,
    )  # fmt: skip
    if m:
        mon = MONTHS[m.group(1)[:3]]
        d1 = int(m.group(2))
        mon2 = MONTHS[m.group(3)[:3]] if m.group(3) else mon
        d2 = int(m.group(4)) if m.group(4) else d1
        if not (1 <= d1 <= 31 and 1 <= d2 <= 31):
            return f"{y:04d}-{mon:02d}", ""
        return f"{y:04d}-{mon:02d}-{d1:02d}", f"{y:04d}-{mon2:02d}-{d2:02d}"
    m = re.search(MONTH + r",?\s+(19|20)\d{2}", t) or re.search(MONTH, t)
    if m:
        return f"{y:04d}-{MONTHS[m.group(1)[:3]]:02d}", ""
    return (f"{y:04d}", "") if ym else ("", "")


def strip_date(text: str) -> str:
    t = re.sub(r"(?i)\(?\b" + MONTH + r"\s+\d{1,2}.*$", "", text)
    t = re.sub(r"(?i)\b" + MONTH + r",?\s+(19|20)\d{2}.*$", "", t)
    t = re.sub(r"\s*\(([^)]*)$", r", \1", t)  # "Newport NOOD (Newport, RI" -> "..., Newport, RI"
    return t.strip(" ,-–(")


def remove_date(text: str) -> str:
    t = re.sub(r"(?i)\(?\b" + MONTH + r"\s+\d{1,2}[^,)]*(,\s*(19|20)\d{2})?\)?", "", text)
    t = re.sub(r"(?i)\b" + MONTH + r",?\s+(19|20)\d{2}", "", t)
    return re.sub(r"\s*,\s*,", ",", t).strip(" ,")


def location(name: str) -> tuple[str, str, str]:
    """(city, state, country) from an event name such as "NAs, Annapolis, MD"."""
    low = name.lower()
    for k, c in ABROAD.items():
        if k in low:
            return "", "", c
    parts = [p.strip() for p in name.split(",")]
    for i in range(len(parts) - 1, 0, -1):
        code = state_code(parts[i])
        if len(code) == 2 and (parts[i].strip().upper() == code or parts[i].lower() in NAMES):
            city = parts[i - 1] if i - 1 > 0 else ""
            return city, code, "CAN" if code in CANADA else "USA"
    for k, st in VENUES.items():
        if k in low:
            return "", st, "CAN" if st in CANADA else "USA"
    return "", "", ""


def is_dated(text: str) -> bool:
    return bool(re.search(r"(?i)\b" + MONTH + r"|\b(19|20)\d{2}\b", text))


def is_month_only(text: str) -> bool:
    return bool(re.fullmatch(r"(?i)\s*" + MONTH + r",?\s*((19|20)\d{2})?\s*", text))


# --- rows --------------------------------------------------------------------------------


def _role(cell: str) -> str:
    c = re.sub(r"\s+", " ", cell.strip().lower().strip("|:"))
    if not c:
        return ""
    if RACE.match(c):
        return "race"
    for role, pat in ROLES:
        if re.fullmatch(pat, c):
            return role
    return "?"


def header_roles(cells: list[str]) -> list[str] | None:
    """Roles for a header row, or None if this isn't one (needs a name and a total column)."""
    roles = [_role(c) for c in cells]
    # "Pos." over every race column and again after the score: only the last is the place.
    pl = [i for i, r in enumerate(roles) if r == "place"]
    for i in pl[:-1] if len(pl) > 2 else []:
        roles[i] = "race"
    # "Total | Nett": the gross total is not the score.
    nett = [i for i, c in enumerate(cells) if re.fullmatch(r"(?i)\s*nett?\s*", c)]
    if nett:
        roles = ["" if r == "total" and i not in nett else r for i, r in enumerate(roles)]
    names = {"boat", "skipper"} & set(roles)
    if names and ("total" in roles or roles.count("race") >= 2) and roles.count("?") <= 3:
        # A leading "No." is the place; elsewhere it is a race count (Block Island "NO").
        return [r if not (r == "place" and i > 0 and cells[i].strip(".").lower() == "no") else ""
                for i, r in enumerate(roles)]  # fmt: skip
    return None


def text_header(line: str) -> list[str] | None:
    """Roles of a text header line in order (used as hints), e.g. Pl Sail Skipper Boat T."""
    if re.match(r"\s*\d", line) or re.search(r"\b[a-z]{3,} [a-z]{2,} [a-z]{2,} [a-z]{3,}\b", line):
        return None  # a result row ("144 Elizabeth Bill Helming ...") or prose
    low = line.lower().replace("|", " ")
    toks = re.findall(r"[a-z#/'().]+|\d+", low)
    order: list[str] = []
    joined = " ".join(toks)
    for role, pat in (
        ("place", r"^(pl|pos|place|position|rank|no\.?)\b"),
        ("sail", r"\b(sail|hull|bow/sail)\b"),
        ("boat", r"\b(boat|yacht)"),
        ("skipper", r"\b(skipper|owner|helm|entrant)"),
        ("home", r"\b(from|home|address|port)\b"),
        ("club", r"\bclub\b"),
        ("total", r"\b(total|tot|points|pts|t)\b"),
        ("fin", r"\b(fin|pos)\b\W*$"),
    ):
        m = re.search(pat, joined)
        if m:
            order.append((m.start(), role))  # type: ignore[arg-type]
    if not ({"boat", "skipper"} & {r for _, r in order}):  # type: ignore[misc]
        return None
    if not re.search(r"\b(total|tot|points|pts|t|r\s?1|1|#1|race)\b", joined):
        return None
    roles = [r for _, r in sorted(order)]  # type: ignore[misc]
    # Total printed before the race columns ("T 1 2 3", "Total R1 R2").
    m_tot = re.search(r"\b(total|tot|points|pts|t)\b", joined)
    m_race = re.search(r"\b(r\s?-?1|1|#1|race\s?1)\b", joined)
    if m_tot and m_race and m_tot.start() < m_race.start():
        roles.append("total_first")
    return roles


def is_score(cell: str) -> bool:
    c = cell.strip()
    if not c:
        return False
    return all(SCORE_TOKEN.match(t) for t in re.split(r"\s+", c))


def _num(s: str) -> float | None:
    m = NUMBER.search(s.replace(",", "."))
    return float(m.group(0)) if m else None


COUNTRY_SAIL = re.compile(r"(?i)\s*(usa|us|can|ber|gbr)\s*-?\s*(\d{1,6})\s*")


def sail_country(cell: str) -> str:
    """ "USA 17" -> "USA", "CAN565" -> "CAN"; "" when no prefix is printed."""
    m = re.match(r"(?i)\s*(?:\d{1,3}\s*/\s*)?(usa|us|can|ber|gbr)\s*-?\s*\d", cell)
    return {"US": "USA"}.get(m.group(1).upper(), m.group(1).upper()) if m else ""


def _digits(s: str) -> str:
    """First run of digits in a sail cell the patterns don't cover ("17 29": sail, then bow)."""
    m = re.search(r"\d{1,6}", s)
    return m.group(0) if m else ""


def _last_num(s: str) -> float | None:
    found = NUMBER.findall(s)
    m = list(NUMBER.finditer(s))
    return float(m[-1].group(0)) if found else None


def _place(cell: str) -> int | None:
    m = PLACE.match(cell.strip())
    return int(m.group(2)) if m else None


def _sail(cell: str) -> str | None:
    c = cell.strip()
    # "Bow/Sail" as "45/ 93105" or "36/ CAN 110"; "524J", "284z" carry a scorer's flag letter.
    m = re.fullmatch(r"(?i)(\d{1,3})\s*/\s*(?:[a-z]{2,3}\s*)?(\d{1,6})", c) or re.fullmatch(
        r"(?i)()(\d{1,6})[a-z]", c
    )
    if m:
        return m.group(2)
    m = SAIL.match(c)
    if m:
        digits = m.group(3) or ""
        if c == "???" or (digits.startswith("0") and len(digits) <= 2):
            return ""  # unknown, or a bow number such as "08"
        return digits.lstrip("0")  # "059" -> "59"
    return None


def _split_caps(tokens: list[str]) -> list[str]:
    """Split a run of words into an ALL-CAPS part and the rest ("GRINGO Glaze,Ryan")."""
    runs: list[list[str]] = []
    prev = None
    for t in tokens:
        if not any(ch.isalpha() for ch in t) and prev is not None:
            runs[-1].append(t)  # "ADVANTAGE 3", "Bergmann / Bennett"
            continue
        caps = t.upper() == t and (len(t) > 1 or bool(prev))  # "MARIAN V": V stays with MARIAN
        if prev is None or caps != prev:
            runs.append([t])
        else:
            runs[-1].append(t)
        prev = caps
    return [" ".join(r) for r in runs]


CITY_PREFIX = {"new", "st", "st.", "san", "los", "port", "east", "west", "north", "south", "fort",
               "ft", "ft.", "grosse", "lake", "little", "oyster", "glen", "sag", "red", "ocean",
               "great", "old", "cape", "long", "palm", "santa", "el", "la"}  # fmt: skip


def _split_home(text: str) -> tuple[str, str]:
    """ "Emery, Damien Shoreham, NY" -> ("Emery, Damien", "Shoreham, NY"); ("", "") if no city."""
    m = re.match(r"^(.*?)\s*\b([\w.'-]+), ([A-Z]{2})$", text)
    if not m or not m.group(1):
        return "", ""
    before, city = m.group(1).split(), m.group(2)
    if before and before[-1].lower() in CITY_PREFIX:
        city = before.pop() + " " + city
    return " ".join(before), f"{city}, {m.group(3)}"


def _caps_pair(tokens: list[str]) -> list[str]:
    """Two names only when one is ALL CAPS and the other isn't ("GRINGO Glaze,Ryan")."""
    parts = _split_caps(tokens)
    if len(parts) == 2 and parts[0].isupper() != parts[1].isupper():
        return parts
    return [" ".join(tokens)]


def _split_one(text: str, hint: list[str]) -> tuple[list[str], bool]:
    """Split "Gigi David Wagner" (boat then skipper, single spaces) by header order.

    Sure only when the skipper comes last and starts with a common first name ("David
    Wagner", "Dennis & Sharon Case"); otherwise a two-word guess that callers treat as unsure.
    """
    toks = text.split()
    if len(toks) < 3:
        return [text], False
    if hint.index("boat") < hint.index("skipper"):
        for i in range(1, len(toks) - 1):
            if toks[i].lower().strip(".,") in FIRST_NAMES and len(toks) - i <= 5:
                return [" ".join(toks[:i]), " ".join(toks[i:])], True
        return [" ".join(toks[:-2]), " ".join(toks[-2:])], False
    return [" ".join(toks[:2]), " ".join(toks[2:])], False  # header order: skipper, boat


FIRST_NAMES = set(
    """
al alan alec alex alexander andrew andy anne arthur barry ben bernard bill bob bo brad brian
bruce carl charles charlie chris chuck colin craig dale damian damien dan daniel dave david
dean dennis dick don donald doug douglas ed eric fred frank gary geoff george glen glenn greg
harry hal howard howie hugh ian jack james jamie jay jeff jeffrey jerry jim jimmy joe joerg
john jon jonathan josh judy ken kevin kirk larry lee len lenny lewis malcolm marc mark marty
matt matthew michael mike nelson norma pam pat patrick paul pete peter phil philip ralph randy
rick richard rob robert rod roger ron roy russ sam scott sean stan steve steven stewart sue
susan ted terry thomas tim tom tommy tony vic victor walter wayne will william worth
""".split()  # noqa: SIM905
)


def _person_score(s: str) -> int:
    """Positive if ``s`` looks like a person's name, negative if like a boat's."""
    score = 0
    first = re.split(r"[\s,./&]+", s.strip().lower())
    if first and first[0] in FIRST_NAMES:
        score += 3
    if (
        len(first) > 1
        and re.match(r"^[a-z'-]+,\s?[a-z]", s.strip().lower())
        and first[1] in FIRST_NAMES
    ):
        score += 3
    if re.search(r"(?i)^[a-z]\.\s|\b[a-z]\.\s?[A-Z]|,\s?[A-Z]|/|&| and ", s):
        score += 2
    if s.isupper() and len(s) > 2:
        score -= 1
    if re.search(r"\d|['!?]", s):
        score -= 1
    return score


class Section:
    """Rows under one heading; parses the J/105 result blocks it holds."""

    def __init__(self, year: int, heading: str, anchor: str) -> None:
        self.year = year
        self.heading = heading
        self.anchor = anchor
        self.items: list[tuple[str, Any]] = []

    def blocks(self) -> list[tuple[str, list[Result]]]:
        out: list[tuple[str, list[Result]]] = []
        label = ""
        other = False
        hdr: list[str] | None = None  # table header roles
        hint: list[str] | None = None  # text header hints
        spans: list[tuple[int, str, int]] | None = None  # (start, role, end or -1) <pre> columns
        recent: list[str] = []  # last text lines, for multi-line <pre> headers
        rows: list[Result] = []
        names: list[list[str]] = []  # unordered name cells per row, for the boat/skipper vote

        def close() -> None:
            nonlocal rows, names
            if rows:
                _sail_first(rows)
                _sail_column(rows)
                start = 0
                for i in range(1, len(rows) + 1):
                    if i == len(rows) or (rows[i]["place"] == 1 and rows[i - 1]["place"] > 1):
                        part, pn = rows[start:i], names[start:i]
                        self._assign_names(part, pn, hint)
                        out.append((label, part))
                        start = i
            for r in rows:
                r.pop("_alt", None)  # type: ignore[misc]
                r.pop("_sf", None)  # type: ignore[misc]
                r.pop("_ssail", None)  # type: ignore[misc]
                r.pop("_maybe_sail", None)  # type: ignore[misc]
                r.pop("_unknown_sail", None)  # type: ignore[misc]
            rows, names = [], []

        if any(k == "t" and "SKIPPER, ETC" in v[0] for k, *v in self.items):
            return self._yrss()
        for kind, *val in self.items:
            if kind == "t":
                val = [re.sub(r"(\d\.\d\d)(\d)", r"\1 \2", val[0]), val[1]]
            if kind == "r":
                cells = val[0]
                roles = header_roles(cells)
                if roles:
                    close()
                    hdr, hint = roles, None
                    continue
                parsed = self._table_row(cells, hdr)
            else:
                line, pre = val
                if pre and re.fullmatch(r"[\s|-]*-{3,}[\s|-]*", line) and recent:
                    sp = dash_spans(line, recent[-3:])
                    if sp and spans and text_header(recent[-1]):
                        # Prefer the header word that starts inside each dashed group.
                        sp = [
                            (a, next((r for st, r, _ in spans if a - 1 <= st < b and r), role), b)
                            for a, role, b in sp
                        ]
                    if sp:
                        close()
                        spans, hdr = sp, None
                        hint = [r for _, r, _ in sp]
                    continue
                h = text_header(line)
                if h:
                    close()
                    hint, hdr = h, None
                    spans = word_spans(line, recent[-1] if recent else "") if pre else None
                    recent.append(line)
                    continue
                recent.append(line)
                parsed = self._positional(line, spans) if pre and spans else None
                if parsed is None:
                    parsed = self._text_row(line, pre, hint)
                if parsed is None and rows and self._continuation(line, rows[-1]):
                    continue
            if parsed is None:
                lab = self._label(kind, val)
                if lab is not None:
                    close()
                    label, other = lab, bool(OTHER_CLASS.search(lab)) and not J105.search(lab)
                continue
            res, name_cells, row_class = parsed
            if row_class and not J105.search(row_class):
                continue
            if other:
                continue
            rows.append(res)
            names.append(name_cells)
        close()
        return out

    def _yrss(self) -> list[tuple[str, list[Result]]]:
        """ "Yacht Race Scoring Systems" pages: three lines per boat (skipper / sail + total,
        place / boat), records separated by dashed rules. "1.0012.00"-style gluing is split."""
        label = ""
        out: list[tuple[str, list[Result]]] = []
        rows: list[Result] = []
        rec: list[str] = []

        recs: list[tuple[str, str, str, str, float | None, int, int, list[str]]] = []
        throw = any(k == "t" and "THROW" in v[0].upper() for k, *v in self.items)

        def flush() -> None:
            if len(rec) >= 2:
                l1 = rec[0].split("|")[0].strip()
                m = re.fullmatch(r"(.*?)\s*(\d{1,6})?", rec[1].split("|")[0].strip())
                l2, sail = (m.group(1).strip(), m.group(2) or "") if m else ("", "")
                l3 = rec[2].split("|")[0].strip() if len(rec) > 2 else ""
                tail = rec[1].split("||")[-1].split("|") if "||" in rec[1] else []
                races = [c.strip() for c in rec[0].split("||")[0].split("|")[1:]]
                # Line 1 holds finishing places; line 3, when present, the points scored.
                pts = rec[2].split("||")[0].split("|")[1:] if len(rec) > 2 else []
                if len(pts) == len(races):
                    races = [c.strip() for c in pts]
                place = _place(tail[1].strip()) if len(tail) >= 2 else None
                if place and l1:
                    n = sum(1 for c in races if re.fullmatch(r"\d+(\.\d+)?", c))
                    if throw:  # last column before "||" is the discarded race's number
                        races = races[:-1]
                    recs.append((l1, l2, l3, sail, _num(tail[0]), place, n, races))
            rec.clear()

        for kind, *val in self.items:
            if kind != "t":
                continue
            line = val[0]
            if "Time:" in line and J105.search(line):
                label = J105.search(line).group(0)  # type: ignore[union-attr]
            if re.match(r"^-{5,}", line.strip()):
                flush()
                continue
            if "|" in line and not re.search(r"(?i)skipper, etc|race \d|finish|points", line):
                rec.append(line)
        flush()
        # Line order varies by scorer: skipper / sail / boat, or boat (or skipper) / skipper
        # (or boat) + sail / home. Decide per block which of lines 1 and 2 is the person.
        vote = sum(_person_score(l1) - _person_score(l2) for l1, l2, *_ in recs if l2)
        for l1, l2, l3, sail, net, place, n, races in recs:
            if not l2:
                skipper, boat, home = l1, l3, ""
            elif vote > 0:
                skipper, boat, home = l1, l2, l3
            else:
                skipper, boat, home = l2, l1, l3
            r: Result = {"sail": sail, "sail_country": "", "boat": boat, "skipper": skipper,
                         "club": "", "net": net, "place": place, "races_sailed": n}  # fmt: skip
            if home:
                r["home"] = home
            scores = race_list(races)
            if scores:
                r["race_scores"] = scores
            rows.append(r)
        if rows:
            out.append((label or "J/105", rows))
        return out

    # A short line or row naming a class or fleet ("J 105 (34 boats)", "Class F - J/105", "Gold").
    def _label(self, kind: str, val: list[Any]) -> str | None:
        text = " ".join(c for c in val[0] if c) if kind == "r" else val[0]
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) > 90:
            return None
        if (
            J105.search(text)
            or OTHER_CLASS.search(text)
            or re.fullmatch(
                r"(?i)(gold|silver|bronze|overall|fleet\b.*|division\b.*|class\b.*)", text
            )
        ):
            return text
        return None

    def _table_row(self, cells: list[str], hdr: list[str] | None) -> Any:
        if hdr:
            row = cells
            if len(row) != len(hdr):
                row = [c for c in cells if c]
                h = [r for r in hdr if r != ""]
                if len(row) != len(h):
                    return self._heuristic([c for c in cells if c], self._hint_from(hdr))
            else:
                h = hdr
            return self._mapped(row, h)
        return self._heuristic([c for c in cells if c], None)

    @staticmethod
    def _hint_from(hdr: list[str]) -> list[str]:
        out = [r for r in hdr if r in ("place", "sail", "boat", "skipper", "home", "club")]
        if "total" in hdr and "race" in hdr and hdr.index("total") < hdr.index("race"):
            out.append("total_first")
        if hdr and hdr[-1] == "place" and "total" in hdr:
            out.append("fin")
        return out

    def _mapped(self, row: list[str], roles: list[str]) -> Any:
        get: dict[str, str] = {}
        for r, c in zip(roles, row, strict=True):
            if r and r not in get and c.strip():
                get[r] = c.strip()
        place = _place(get.get("place", ""))
        if place is None:
            return None
        total = _num(get["total"]) if get.get("total") else None
        races = [c for r, c in zip(roles, row, strict=True) if r == "race" and c.strip()]
        if total is None and not races:
            return None
        hashed = "sail" not in get and "hash" in get
        if hashed:
            get["sail"] = get["hash"]
        # "USA 332" printed in the boat column is a sail number (the boat name may be absent).
        m = COUNTRY_SAIL.fullmatch(get.get("boat", ""))
        if m and (hashed or not get.get("sail")):
            get["sail"], hashed = get["boat"], False
        sail = _sail(get.get("sail", ""))
        res: Result = {
            "sail": sail if sail is not None else _digits(get.get("sail", "")),
            "sail_country": sail_country(get.get("sail", "")),
            "boat": get.get("boat", ""),
            "skipper": get.get("skipper", ""),
            "club": get.get("club", ""),
            "net": total,
            "place": place,
        }
        if get.get("home"):
            res["home"] = get["home"]
        if hashed:
            res["_hash"] = get["hash"]  # type: ignore[typeddict-unknown-key]
        if races:
            res["races_sailed"] = sum(
                1 for c in races if re.fullmatch(r"[\(\[]?\d+(\.\d+)?[\)\]]?", c)
            )
            scores = race_list([c for r, c in zip(roles, row, strict=True) if r == "race"])
            if scores:
                res["race_scores"] = scores
        return res, [], get.get("class", "")

    def _positional(self, line: str, spans: list[tuple[int, str, int]]) -> Any:
        """Read a fixed-width ``<pre>`` row by the column each word sits under."""
        cols: dict[int, list[str]] = {}
        starts = [st for st, _, _ in spans]
        for m in re.finditer(r"\S+", line.replace("|", " ")):
            centre = (m.start() + m.end() - 1) / 2
            inside = [i for i, (a, _, b) in enumerate(spans) if a <= centre < b]
            if inside:
                cols.setdefault(inside[0], []).append(m.group(0))
                continue
            cands = [i for i, st in enumerate(starts) if st <= m.end()] or [0]
            i = min(cands, key=lambda k: abs(starts[k] - centre) if starts[k] <= centre
                    else abs(starts[k] - m.start()) + 0.5)  # fmt: skip
            cols.setdefault(i, []).append(m.group(0))
        get: dict[str, str] = {}
        races: list[str] = []
        race_cells: list[str] = []
        for i, (_, role, end) in enumerate(spans):
            words = cols.get(i, [])
            if role == "race":
                # One column per race under a word header; a dashed group may hold them all.
                race_cells += _split_scores(words) if end >= 0 else [" ".join(words)]
            if not words:
                continue
            text = " ".join(words)
            if role == "race":
                races += words
            elif role == "total+place":
                nums = [w for w in words if _num(w) is not None]
                if nums:
                    get.setdefault("total", nums[0])
                if len(nums) > 1:
                    get.setdefault("place", nums[1])
            elif role:
                get.setdefault(role, text)
        if "place" not in get:  # place printed in the first column, e.g. "   1 JAVA   58"
            first = get.get("boat") or get.get("skipper") or ""
            m = re.match(r"^(\d{1,3})\.?\s+(.*)$", first)
            for key in ("sail", "boat", "skipper"):
                v = get.get(key, "")
                m = re.match(r"^(\d{1,3})\.?\s+(\D.*)$", v)
                if m:
                    get["place"], get[key] = m.group(1), m.group(2)
                    break
        if get.get("skipper") and not get.get("boat"):
            parts = _split_caps(get["skipper"].split())
            if len(parts) == 2 and parts[1].isupper() and not parts[0].isupper():
                get["skipper"], get["boat"] = parts
        if get.get("sail") and _sail(get["sail"]) is None:
            m = re.match(r"^(\d{1,6})\s+(\D.*)$", get["sail"])  # "90 PLUM CRAZY"
            if m and not get.get("boat"):
                get["sail"], get["boat"] = m.group(1), m.group(2)
        place = _place(get.get("place", ""))
        total = _num(get["total"]) if get.get("total") else None
        if (
            place is None
            or (total is None and not races)
            or not (get.get("boat") or get.get("skipper"))
        ):
            return None
        hashed = "sail" not in get and "hash" in get
        if hashed:
            get["sail"] = get["hash"]
        # "USA 332" printed in the boat column is a sail number (the boat name may be absent).
        m = COUNTRY_SAIL.fullmatch(get.get("boat", ""))
        if m and (hashed or not get.get("sail")):
            get["sail"], hashed = get["boat"], False
        sail = _sail(get.get("sail", ""))
        res: Result = {"sail": sail or "", "sail_country": sail_country(get.get("sail", "")),
                       "boat": get.get("boat", ""),
                       "skipper": get.get("skipper", ""), "club": get.get("club", ""),
                       "net": total, "place": place}  # fmt: skip
        if get.get("home"):
            res["home"] = get["home"]
        res["races_sailed"] = sum(1 for w in races if re.fullmatch(r"\d+(\.\d+)?", w))
        scores = race_list(race_cells)
        if scores:
            res["race_scores"] = scores
        return res, [], ""

    def _text_row(self, line: str, pre: bool, hint: list[str] | None) -> Any:
        s = line.replace("|", " ").strip()
        # Comma formats: "1. Ian Charles, SAILS CALL, #112", "1. Junto, J 105 34, M Morin, ...".
        m = re.match(r"^(\d{1,3})\.\s+(.+)$", s)
        if m and "," in m.group(2) and not re.search(r"\s{2,}", m.group(2)):
            return self._comma_row(int(m.group(1)), m.group(2))
        cells = re.split(r"\t+|\s{2,}", s) if pre or "\t" in s else s.split()
        cells = [c.strip() for c in cells if c.strip()]
        if not pre and "\t" not in s:
            return self._heuristic(cells, hint, tokens=True)
        return self._heuristic(cells, hint)

    def _comma_row(self, place: int, rest: str) -> Any:
        total = None
        races = 0
        m = re.search(r"\s[-–]\s*([\d\s,/()-]+);\s*([\d.]+)\s*$", rest) or re.search(
            r",\s*([\d-]+);\s*([\d.]+)\s*$", rest
        )
        cells: list[str] = []
        if m:
            total = float(m.group(2))
            cells = re.findall(r"[\(\[]?\d+(?:\.\d+)?[\)\]]?", m.group(1))
            races = len(cells)
            rest = rest[: m.start()]
        m2 = re.search(r"=\s*([\d.]+)", rest)
        if total is None and m2:
            total = float(m2.group(1))
        parts = [p.strip() for p in rest.split(",") if p.strip()]
        sail = ""
        boat = skipper = home = ""
        paren = re.match(r"^(.+?)\s*\((.+?)\)", rest)
        if paren and total is not None:  # "Good Timin (Chris & Phil Perkins) with ... = 8"
            boat, skipper = paren.group(1), paren.group(2)
        else:
            keep = []
            for p in parts:
                if re.fullmatch(r"(?i)j\s*[/-]?\s*105\s+\d+", p):
                    continue  # "J 105 34": class and a constant (length?), not the sail
                ms = re.fullmatch(r"#?\s*(\d{1,6})", p)
                if ms and not sail:
                    sail = ms.group(1)
                elif J105.fullmatch(p.strip()):
                    continue
                else:
                    keep.append(p)
            if len(keep) >= 2:
                a, b = keep[0], keep[1]
                if _person_score(a) > _person_score(b) or (b.isupper() and not a.isupper()):
                    skipper, boat = a, b
                else:
                    boat, skipper = a, b
                home = ", ".join(keep[2:4])
            elif keep:
                boat = keep[0]
        res: Result = {
            "sail": sail,
            "sail_country": "",
            "boat": boat.strip(),
            "skipper": skipper.strip(),
            "club": "",
            "net": total,
            "place": place,
        }
        if home:
            res["home"] = home
        if races:
            res["races_sailed"] = races
            scores = race_list(cells)
            if scores:
                res["race_scores"] = scores
        return res, [], ""

    def _heuristic(self, cells: list[str], hint: list[str] | None, tokens: bool = False) -> Any:
        if len(cells) < 3:
            return None
        hint = hint or []
        fin = "fin" in hint
        place = _place(cells[0])
        body = cells[1:]
        first_sail = _sail(cells[0]) if place is None else None
        sail_first = False
        drop_last = 0
        if place is None and not fin and not first_sail:
            return None
        # Trailing scores.
        i = len(body)
        while i > 0 and is_score(body[i - 1]):
            i -= 1
        scores, mid = body[i:], body[:i]
        scores = _split_scores(scores)  # "71 10" under a 2-space split: sail, then a race
        nums = [s for s in scores if _num(s) is not None and s.strip() not in ("-", "--")]
        if place is None:
            if len(nums) < 2:
                return None
            place = _place(nums[-1].strip())
            if place is None:
                return None
            nums = nums[:-1]
            mid = cells[: len(cells) - len(scores)]
            sail_first = True
            drop_last = 1
            if len(nums) < 1:
                return None
        elif fin and len(nums) >= 2 and _place(nums[-1]) == place:
            nums = nums[:-1]
            drop_last = 1
        if not nums or not mid:
            return None
        # Header "Boat Skipper Sail Pts 1 2 …": the sail is the first number after the names.
        order = [r for r in hint if r in ("boat", "skipper", "sail")]
        suffix_sail = ""
        if (
            len(order) >= 2
            and order[-1] == "sail"
            and len(nums) >= 2
            and re.fullmatch(r"\d{1,6}", nums[0].strip())
            and not any(_sail(c) is not None for c in mid)
        ):
            suffix_sail, nums = nums[0].strip(), nums[1:]
        elif (
            not hint
            and len(nums) >= 3
            and re.fullmatch(r"\d{3,6}|\?\?\?", nums[0].strip())
            and not any(_sail(c) is not None for c in mid)
        ):
            # "Thomas Carruthers  Clouseau  275  2 1 1 6 2 - 12": no race scores 100+.
            suffix_sail, nums = nums[0].strip(), nums[1:]
        maybe_sail = (
            not hint
            and not suffix_sail
            and len(nums) >= 3
            and bool(re.fullmatch(r"\d{1,2}", nums[0].strip()))
            and not any(_sail(c) is not None for c in mid)
        )
        races = race_list(
            _races_from(scores, drop_last, 1 if suffix_sail else 0, "total_first" in hint)
        )
        if "total_first" in hint:
            total = _num(nums[0])
            race_cells = nums[1:]
        else:
            total = _last_num(nums[-1].replace("/", ""))
            race_cells = nums[:-1]
        # Middle: sail, class, home, club and names.
        sail = country = ""
        row_class = ""
        name_parts: list[str] = []
        home = club = ""
        if tokens:
            mid = self._token_cells(mid)
        merged: list[str] = []
        for c in mid:  # "M.  SORENSEN" split by the double space
            if merged and re.fullmatch(r"[A-Za-z]\.|[A-Za-z]\.&\s?[A-Za-z]\.", merged[-1]):
                merged[-1] += " " + c
            else:
                merged.append(c)
        mid = merged
        prefixed = [i for i, c in enumerate(mid) if COUNTRY_SAIL.fullmatch(c)]
        same = (
            prefixed
            and any(
                c.strip() == COUNTRY_SAIL.fullmatch(mid[prefixed[0]]).group(2)  # type: ignore[union-attr]
                for c in mid[: prefixed[0]]
            )
        )
        # "370 | USA 370 | Petkovic" has a boat named "USA 370"; only a different bare number
        # before "USA nnn" is a bow number.
        if prefixed and not sail and not same:
            i = prefixed[0]
            sail, country = _sail(mid[i]) or "", sail_country(mid[i])
            # "1. | 30 | USA 658 | Big Booty | Patrick Eudy": 30 is the bow number.
            mid = [c for c in mid[:i] if not re.fullmatch(r"\d{1,3}", c.strip())] + mid[i + 1 :]
        hashed = [c for c in mid if re.fullmatch(r"#\s*\d{1,6}", c.strip())]
        if hashed and not sail:
            sail = hashed[0].strip("# ")
            mid = [c for c in mid if c is not hashed[0]]
        for c in mid:
            s = _sail(c)
            if s is not None and not sail:
                sail, country = s, sail_country(c)
                continue
            m = re.fullmatch(r"(?i)(j\s*[/-]?\s*105)\s+(\d{1,6})", c)
            if m:
                sail = sail or m.group(2)
                continue
            if J105.fullmatch(c) or re.fullmatch(r"(?i)j\s*[/-]?\s*\d{2,3}", c):
                row_class = c
                continue
            m = re.match(r"^(#?\d{1,6})\s+(\D.*)$", c)  # "90 PLUM CRAZY"
            if m and not sail:
                sail = m.group(1).lstrip("#")
                name_parts.append(m.group(2))
                continue
            if (
                HOME.search(c)
                and len(name_parts) >= 1
                and not PERSONISH.search(c.split(",")[0] + ",")
            ):
                home = c
                continue
            m = re.match(r"^(.*?)\s*#\s*(\d{1,6})$", c)  # "XSNRJ #150"
            if m and not sail and m.group(1):
                sail = m.group(2)
                c = m.group(1)
            name_parts.append(c)
        sail = sail or (suffix_sail if suffix_sail != "???" else "")
        unsure = tokens and len(name_parts) > 2 and not ({"home", "club"} & set(hint))
        if len(name_parts) == 1 and (
            {"boat", "skipper"} <= set(hint) or (tokens and len(name_parts[0].split()) >= 3)
        ):
            order_hint = hint if {"boat", "skipper"} <= set(hint) else ["boat", "skipper"]
            name_parts, sure = _split_one(name_parts[0], order_hint)
            unsure = not sure
        # Drop a club when the header lists one, or a trailing "Lakewood Y C".
        if "club" in hint and len(name_parts) >= 3:
            club = name_parts.pop(hint_index(hint, "club", name_parts))
        elif len(name_parts) >= 3 and CLUB.search(name_parts[-1]):
            club = name_parts.pop()
        if "home" in hint and len(name_parts) >= 3 and not home:
            home = name_parts.pop(hint_index(hint, "home", name_parts))
        if not name_parts:
            return None
        res: Result = {"sail": sail, "sail_country": country, "boat": "", "skipper": "",
                       "club": club, "net": total, "place": place}  # fmt: skip
        if home:
            res["home"] = home
        res["races_sailed"] = sum(1 for c in race_cells if re.fullmatch(r"\d+(\.\d+)?", c.strip()))
        if races:
            res["race_scores"] = races
        if sail_first:
            res["_sf"] = True  # type: ignore[typeddict-unknown-key]
        if not hint and any(c.strip() == "???" for c in mid):
            res["_unknown_sail"] = True  # type: ignore[typeddict-unknown-key]
        if suffix_sail and not hint:
            res["_ssail"] = True  # type: ignore[typeddict-unknown-key]
        if maybe_sail:
            res["_maybe_sail"] = nums[0].strip()  # type: ignore[typeddict-unknown-key]
        if unsure:
            res["_unsure"] = True  # type: ignore[typeddict-unknown-key]
        # Rows may instead read "sail … total place": kept for _sail_first() to check per block.
        last = _place(nums[-1].strip()) if nums else None
        if (
            not sail_first
            and _sail(cells[0])
            and cells[0].strip().isdigit()
            and last is not None
            and "total_first" not in hint
        ):
            prev = _last_num(nums[-2]) if len(nums) > 1 else None
            res["_alt"] = (cells[0].strip(), last, prev)  # type: ignore[typeddict-unknown-key]
        return res, name_parts[:2], row_class

    @staticmethod
    def _token_cells(tokens: list[str]) -> list[str]:
        """Join single-space tokens into cells: sail numbers stand alone, words form runs."""
        out: list[str] = []
        run: list[str] = []
        seen_sail = False
        for t in tokens:
            if (_sail(t) is not None and not seen_sail) or J105.fullmatch(t):
                seen_sail = seen_sail or _sail(t) is not None
                if run:
                    out += _caps_pair(run)
                    run = []
                out.append(t)
            else:
                run.append(t)
        if run:
            out += _caps_pair(run)
        return out

    def _continuation(self, line: str, last: Result) -> bool:
        """A home-port line under a result ("    Sandusky Ohio       #39")."""
        s = line.strip()
        if not s or _place(s.split()[0]) is not None or len(s) > 60 or not line[:1].isspace():
            return False
        if re.search(r"(?i)throw|=|\*|race|protest|\bdn[cfs]\b|\bsee\b|\.com|website|\.$", s):
            return False
        if any(_num(t) is not None and not t.startswith("#") for t in s.split()):
            return False
        m = re.search(r"#\s*(\d{1,6})", s)
        if m and not last["sail"]:
            last["sail"] = m.group(1)
        home = re.sub(r"#\s*\d+", "", s).strip(" ,")
        if home and "home" not in last:
            last["home"] = re.sub(r"\s{2,}", " ", home)
        return True

    def _assign_names(
        self, rows: list[Result], names: list[list[str]], hint: list[str] | None
    ) -> None:
        """Decide which name cell is the boat: from the header order, else a vote over rows."""
        order = [r for r in (hint or []) if r in ("boat", "skipper")]
        boat_first: bool | None = order[0] == "boat" if order else None
        if boat_first is None:
            vote = 0
            for n in names:
                if len(n) >= 2:
                    vote += _person_score(n[1]) - _person_score(n[0])
            boat_first = vote >= 0
        for r, n in zip(rows, names, strict=True):
            if not n:
                continue
            if len(n) == 1:
                r["boat" if boat_first else "skipper"] = n[0]
            else:
                r["boat"], r["skipper"] = (n[0], n[1]) if boat_first else (n[1], n[0])


def _span_role(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower().replace("|", " ")).strip()
    if not t:
        return ""
    totalish = re.search(r"\b(total|totals|points|pts|tot|series|nett?|thru)\b", t)
    if totalish and re.search(r"\b(place|pos|fin)\b", t):
        return "total+place"
    if re.search(r"\b(total|totals|series|thru)\b", t):
        return "total"
    if re.search(r"\b(race|finish)", t):
        return "race"
    if re.search(r"\bclub\b", t):
        return "club"
    if re.search(r"\b(type|rating|affil|strt|class)\b", t):
        return ""
    if re.search(r"\b(skipper|owner|helm|entrant)", t):
        return "skipper"
    if re.search(r"\b(yacht|boat)", t):
        return "boat"
    if re.search(r"\b(sail|hull|id)\b", t):
        return "sail"
    if re.search(r"\b(home|port|city|from|address)\b", t):
        return "home"
    if re.search(r"\b(points|pts|tot|t|nett?|score)\b", t):
        return "total"
    if re.fullmatch(r"(no\.?|pl\.?|place|pos\.?|position|rank|fin|overall place)", t) or re.search(
        r"\b(pos|place|fin)\b", t
    ):
        return "place"
    if re.search(r"\b(r\s?\d+|#\d+)\b|^[\d\s]+$", t):
        return "race"
    return ""


def dash_spans(rule: str, above: list[str]) -> list[tuple[int, str, int]] | None:
    """Columns from a ``---- -------- ----`` rule, named by the header text above each group."""
    groups = [(m.start(), m.end()) for m in re.finditer(r"-+", rule)]
    if len(groups) < 3:
        return None
    out = []
    for a, b in groups:
        text = " ".join(line[a:b] for line in above)
        out.append((a, _span_role(text), b))
    roles = [r for _, r, _ in out]
    if not ({"boat", "skipper"} & set(roles)) or not (
        {"total", "total+place", "race"} & set(roles)
    ):
        return None
    return out


def word_spans(header: str, above: str = "") -> list[tuple[int, str, int]] | None:
    """Columns from a one-line ``<pre>`` header: each label starts a column."""
    out: list[tuple[int, str, int]] = []
    starts = (
        r"(?i)(pl|place|pos|position|rank|no\.?|sail|hull|bow|skipper|owner|helm\w*|entrant"
        r"|boat\w*|yacht|from|home|club|total|tot|t|pts|points|r\s?-?\d+|race|#\d+|\d+|fin|name)$"
    )
    cont = r"(?i)(#|no\.?|name|number|nmbr|port|town|points|pts|#\s*\d*)$"
    for m in re.finditer(r"\S+", header.replace("|", " ")):
        w = m.group(0)
        prev = out[-1] if out else None
        gap = prev is not None and m.start() - prev[2] > 1
        if (
            prev
            and not gap
            and re.fullmatch(cont, w)
            and not re.fullmatch(r"(?i)(no\.?)", w)
            or (
                prev
                and not gap
                and re.fullmatch(r"(?i)no\.?|name", w)
                and prev[1] in ("sail", "boat", "skipper")
            )
        ):
            out[-1] = (prev[0], prev[1], m.end())
            continue
        if prev and not gap and not re.fullmatch(starts, w):
            out[-1] = (prev[0], prev[1], m.end())  # "Skipper(s)", "Owner's"
            continue
        role = "race" if re.fullmatch(r"(?i)(r\s?-?\d+|#\d+|\d+)", w) else _span_role(w)
        if re.fullmatch(r"(?i)name", w):
            role = "boat"
        out.append((m.start(), role, m.end()))
    out = [(st, role, -1) for st, role, _ in out]
    for i, (st, _role, end) in enumerate(out):
        label = re.match(r"\S+", header.replace("|", " ")[st:]).group(0).lower()  # type: ignore[union-attr]
        if label in ("no", "no.") and i > 0:
            over = above.replace("|", " ")[max(0, st - 3) : st + 6].lower()
            out[i] = (st, "sail" if re.search(r"sail|hull", over) else "", end)
    roles = [r for _, r, _ in out]
    if not ({"boat", "skipper"} & set(roles)):
        return None
    return out


def _sail_first(rows: list[Result]) -> None:
    """Switch a block to "sail … total place" when places only make sense read that way."""
    places = [r["place"] for r in rows]
    ok = valid_places(places)
    alts = [
        r.get("_alt") or ((r["sail"], r["place"], r["net"]) if r.get("_sf") else None) for r in rows
    ]
    if ok or not all(alts):
        return
    alt_places = [a[1] for a in alts]  # type: ignore[index]
    if alt_places[0] != 1 or not valid_places(alt_places):
        return
    for r, (sail, place, total) in zip(rows, alts, strict=True):  # type: ignore[misc]
        r["sail"], r["place"], r["net"] = sail, place, total
        if r.get("races_sailed"):
            r["races_sailed"] -= 1
        if r.get("race_scores") and not r.get("_sf"):
            r["race_scores"] = r["race_scores"][:-1]  # its last "race" was the total


def _split_scores(cells: list[str]) -> list[str]:
    """One printed race score per item: "4 13.00" (race, total) splits; "8 DSQ", "- 11 dns",
    "14 p20" stay whole; separators ("-", "--", "=", ";") go."""
    out: list[str] = []
    for c in cells:
        for t in c.split():
            joins = re.fullmatch(r"(?i)[a-z]{2,5}|p\d+", t) or (out and out[-1] in "-([")
            if out and joins and (out[-1] == "-" or not re.fullmatch(r"[-=;.]+", out[-1])):
                out[-1] = f"{out[-1]} {t}"
                continue
            out.append(t)
    return [t for t in out if not re.fullmatch(r"[-=;.|]+|--+", t)]


def race_list(cells: list[str]) -> list[list[Any]] | None:
    """``race_cell`` for each printed race, in order; a leading "-" marks a discard ("- 9")."""
    out = []
    for c in cells:
        t = re.sub(r"(?<![\d.])\.(\d)", r"0.\1", c.strip())  # ".75" is 0.75 points
        if re.match(r"^-\s*\d", t):
            cell = race_cell(t.lstrip("- "))
            cell[2] = True
        else:
            cell = race_cell(t)
        out.append(cell)
    while out and out[-1][0] is None and not out[-1][1]:
        out.pop()  # races not sailed
    # "… 5  [13]  21.0": a trailing bracketed cell repeating a race is the discard column.
    if len(out) > 1 and out[-1][2] and cells[-1].strip().startswith("["):
        same = [x for x in out[:-1] if x[0] == out[-1][0] and not x[2]]
        if same:
            same[-1][2] = True
            out.pop()
    return out or None


def _races_from(scores: list[str], drop_last: int, drop_first: int, total_first: bool) -> list[str]:
    """The race cells among a row's trailing scores, without total, place and sail."""
    cells = _split_scores(scores)
    numeric = [i for i, c in enumerate(cells) if _num(c) is not None]
    gone = set(numeric[len(numeric) - drop_last :] if drop_last else [])
    numeric = [i for i in numeric if i not in gone]
    gone |= set(numeric[:drop_first])
    numeric = numeric[drop_first:]
    if numeric:
        gone.add(numeric[0] if total_first else numeric[-1])
    return [c for i, c in enumerate(cells) if i not in gone]


def _sail_column(rows: list[Result]) -> None:
    """Unlabelled rows with a sail after the names: when most rows show a 3+ digit sail
    there, the 1–2 digit number in the same place on the other rows is a sail too ("45")."""
    sure = sum(1 for r in rows if r.get("_ssail") or r.get("_unknown_sail"))
    rest = [r for r in rows if not (r.get("_ssail") or r.get("_unknown_sail"))]
    if sure * 2 < len(rows) or not all(r.get("_maybe_sail") for r in rest):
        return
    for r in rest:
        r["sail"] = r.pop("_maybe_sail")  # type: ignore[typeddict-item]
        if r.get("race_scores"):
            r["race_scores"] = r["race_scores"][1:]
        if r.get("races_sailed"):
            r["races_sailed"] -= 1


def valid_places(places: list[int]) -> bool:
    """Places 1..n once sorted, ties repeating a place (1, 2, 2, 4)."""
    ps = sorted(places)
    return all(p == i + 1 or (i > 0 and p == ps[i - 1]) for i, p in enumerate(ps))


def hint_index(hint: list[str], role: str, parts: list[str]) -> int:
    names = [r for r in hint if r in ("boat", "skipper", "home", "club")]
    i = names.index(role) if role in names else len(parts) - 1
    return min(i, len(parts) - 1)


def sections(html: bytes | str, year: int) -> list[Section]:
    out: list[Section] = []
    cur = Section(year, "", "")
    for item in stream(html):
        if item[0] == "h":
            out.append(cur)
            cur = Section(year, item[1], item[2])
        else:
            cur.items.append(item)
    out.append(cur)
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def parse_page(html: bytes | str, year: int) -> list[Event]:
    out: list[Event] = []
    ids: set[str] = set()
    parent = ""  # most recent dated heading (event), for undated sub-headings
    parent_anchor = ""
    for sec in sections(html, year):
        head = sec.heading
        blocks = sec.blocks()
        if is_dated(head):
            parent, parent_anchor = head, sec.anchor
            name_src, sub = head, ""
        else:
            # Undated sub-heading: a fleet, division or report under the last dated heading.
            if parent and not is_month_only(parent):
                name_src, sub = parent, head
            else:
                name_src, sub = head + " " + parent, ""
        good = []
        for label, rows in blocks:
            why = implausible(rows)
            if why:
                log.warning("%d %r [%s]: dropped block of %d rows: %s",
                            year, head[:60], label[:30], len(rows), why)  # fmt: skip
            else:
                good.append((label, sorted(rows, key=lambda r: r["place"])))
        if not good and blocks:
            continue
        blocks = good
        if not blocks:
            if _looks_like_results(sec):
                log.warning("%d %r: result-like rows but nothing parsed", year, head[:70])
            continue
        start, end = parse_date(name_src, year)
        name = (
            strip_date(name_src)
            if not (is_month_only(parent) and not sub and name_src != head)
            else strip_date(head)
        )
        if not name:
            name = strip_date(head) or head
        city, state, country = location(remove_date(name_src))
        anchor = sec.anchor or (parent_anchor if sub else "")
        for label, rows in blocks:
            label = re.sub(r"\s+(Date|back to top)\b.*$", "", label)
            cls = " ".join(x for x in (sub, label) if x).strip() or "J/105"
            eid = f"{year}-{_slug(name)}"
            key = f"{eid}/{_slug(cls)}"
            n = 2
            while key in ids:
                key = f"{eid}/{_slug(cls)}-{n}"
                n += 1
            ids.add(key)
            nets = [r["net"] for r in rows]
            for r in rows:
                if not re.search(r"[A-Za-z]", r["club"]):
                    r["club"] = ""
            out.append(
                {
                    "source": "j105org",
                    "event_id": eid,
                    "class_id": key.split("/", 1)[1],
                    "class": cls,
                    "name": name,
                    "start": start,
                    "end": end or start,
                    "city": city,
                    "state": state,
                    "country": country,
                    "location": city,
                    "host": "",
                    "url": page_url(year) + (f"#{anchor}" if anchor else ""),
                    "fleet": len(rows),
                    "races": max((r.get("races_sailed") or 0 for r in rows), default=0),
                    "scored": any(x is not None for x in nets),
                    "results": rows,
                }
            )
    return out


def implausible(rows: list[Result]) -> str:
    """Why a parsed block can't be trusted, or "" if it looks like a results table."""
    unsure = sum(1 for r in rows if r.pop("_unsure", False))  # type: ignore[misc]
    if unsure * 4 > len(rows):
        return f"boat and skipper not separable on {unsure} rows (single-spaced text)"
    places = [r["place"] for r in rows]
    if min(places) != 1:
        return f"first place is {places[0]}"
    if not valid_places(places):
        return f"places out of order {places[:12]}"
    nets = [r["net"] for r in rows]
    if any(n is not None for n in nets):
        if any(n is None for n in nets[:-1]) and sum(n is None for n in nets) > len(nets) // 3:
            return "totals missing"
        known = [n for n in nets if n is not None]
        if any(b < a - 0.01 for a, b in zip(known, known[1:], strict=False)):
            return "totals fall as place rises"
    for r in rows:
        for k in ("boat", "skipper"):
            v = r[k]
            if len(v) > 60 or re.search(r"\b[a-z]{3,} [a-z]{3,} [a-z]{3,} [a-z]{3,}\b", v):
                return f"{k} looks like prose: {v[:40]!r}"
        if not (r["boat"] or r["skipper"]):
            return "row without names"
        if J105.fullmatch(r["club"].strip()):
            return "columns misaligned (class in the club column)"
        if re.search(r"\d", r.get("home", "")):
            return f"numbers in home port {r.get('home')!r}"
        if re.fullmatch(r"[\d.\s]+", r["boat"] or "x") or re.fullmatch(
            r"[\d.\s]+", r["skipper"] or "x"
        ):
            return f"number in a name column: {r['boat']!r} {r['skipper']!r}"
        if r["sail"] and not re.fullmatch(r"\d{1,6}", r["sail"]):
            return f"bad sail {r['sail']!r}"
    return ""


def _looks_like_results(sec: Section) -> bool:
    n = 0
    for kind, *val in sec.items:
        text = " ".join(val[0]) if kind == "r" else val[0]
        if len(re.findall(r"(?<![\d.])\d{1,2}(?![\d.])", text)) >= 4 and re.search(
            r"[A-Za-z]{3}", text
        ):
            n += 1
    return n >= 3


def _boat_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_bow_numbers(events: list[Event]) -> list[str]:
    """Decide, per block, whether a bare "#" column held sail or bow numbers.

    Evidence: boats whose sail is printed under an explicit Sail/Hull column elsewhere in the
    archive. A block is read as bow numbers when its "#" values mostly disagree with those
    sails, or, with no such evidence, when one is written with a leading zero ("08"). Bow
    numbers become sail "".
    """
    known: dict[str, set[str]] = {}
    for e in events:
        for r in e["results"]:
            if r["sail"] and "_hash" not in r and r["boat"]:
                known.setdefault(_boat_key(r["boat"]), set()).add(r["sail"])
    changed = []
    for e in events:
        rows = [r for r in e["results"] if "_hash" in r]
        if not rows:
            continue
        agree = sum(1 for r in rows if r["sail"] in known.get(_boat_key(r["boat"]), ()))
        disagree = sum(
            1
            for r in rows
            if known.get(_boat_key(r["boat"])) and r["sail"] not in known[_boat_key(r["boat"])]
        )
        zeros = any(str(r["_hash"]).strip().startswith("0") for r in rows)  # type: ignore[typeddict-item]
        bow = disagree > agree or (agree == disagree == 0 and zeros)
        for r in rows:
            if bow:
                r["sail"], r["sail_country"] = "", ""
            r.pop("_hash")  # type: ignore[misc]
        kind = "bow numbers" if bow else "sails"
        log.info(
            "%s %s: '#' read as %s (agree %d, disagree %d)",
            e["event_id"], e["class_id"], kind, agree, disagree,
        )  # fmt: skip
        if bow:
            changed.append(f"{e['event_id']}/{e['class_id']}")
    return changed


def standings() -> list[Event]:
    f = _fetcher()
    out: list[Event] = []
    for x in read_json(INDEX, []) or [{"year": y} for y in YEARS]:
        y = x["year"]
        body = f.bytes(page_url(y), cache=f"results/{y}.html")
        if not body:
            continue
        evs = parse_page(body, y)
        log.info("%d: %d J/105 blocks, %d results", y, len(evs), sum(e["fleet"] for e in evs))
        out += evs
    resolve_bow_numbers(out)
    write_json(EVENTS, out)
    return out
