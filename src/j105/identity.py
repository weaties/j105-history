"""Hull identity and person-name handling, driven by the reviewed tables in ``data/identity/``.

A hull's key is its sail number's digits with leading zeros stripped; ``aliases.csv`` maps
known typos, renumbers and PHRF numbers onto one hull, each with a recorded reason.
``optout.csv`` removes or corrects a person's name at build time.
"""

from __future__ import annotations

import csv
import re
from functools import cache
from pathlib import Path

from j105.http import ROOT

TABLES = ROOT / "data" / "identity"
REMOVED = "(name withheld)"


def _rows(name: str, root: Path = TABLES) -> list[dict[str, str]]:
    path = root / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


@cache
def aliases() -> dict[str, str]:
    return {r["sail"]: r["hull"] for r in _rows("aliases.csv")}


@cache
def nicknames() -> dict[str, str]:
    return {r["printed"].lower(): r["name"] for r in _rows("nicknames.csv")}


@cache
def optouts() -> dict[str, tuple[str, str]]:
    return {r["printed"].lower(): (r["action"], r["replacement"]) for r in _rows("optout.csv")}


def sail_key(sail: str) -> str:
    """Digits of a sail number, leading zeros stripped: ``"USA 0475"`` -> ``"475"``.

    Falls back to the stripped text when there are no digits, so nothing is merged by accident.
    """
    digits = re.sub(r"\D", "", sail.split("(")[0]).lstrip("0")
    return digits or sail.strip()


def hull(sail: str, table: dict[str, str] | None = None) -> str:
    key = sail_key(sail)
    return (aliases() if table is None else table).get(key, key)


def tidy(s: str) -> str:
    """Collapse whitespace and fix ALL CAPS or all-lowercase text to title case."""
    s = re.sub(r"\s+", " ", s).strip(" .,/")
    return s.title() if s and (s.isupper() or s.islower()) else s


def person(printed: str) -> str:
    """A skipper name as published, with nicknames resolved and opt-outs applied."""
    p = tidy(printed)
    for nick, name in nicknames().items():
        if nick in p.lower():
            p = name
            break
    action, replacement = optouts().get(p.lower(), ("", ""))
    if action == "remove":
        return REMOVED
    if action == "replace":
        return replacement
    return p
