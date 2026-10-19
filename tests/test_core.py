import datetime as dt

from j105 import identity
from j105.schema import Result, is_recent, rank


def res(sail: str, net: float | None, total: float | None = None) -> Result:
    return {"sail": sail, "sail_country": "", "boat": "", "skipper": "", "club": "",
            "net": net, "total": total, "place": 0}  # fmt: skip


def test_rank_by_net_then_total_missing_last() -> None:
    out = rank([res("a", 10), res("b", None), res("c", 7, 9), res("d", 7, 8)])
    assert [(r["sail"], r["place"]) for r in out] == [("d", 1), ("c", 2), ("a", 3), ("b", 4)]


def test_is_recent() -> None:
    assert is_recent(dt.date.today().isoformat())
    assert not is_recent("2015-06-01")
    assert is_recent("")


def test_sail_key_and_aliases() -> None:
    assert identity.sail_key("USA 0475") == "475"
    assert identity.sail_key("475 (PHRF)") == "475"
    assert identity.sail_key("NA") == "NA"
    table = {"404": "403"}
    assert identity.hull("404", table) == "403"
    assert identity.hull("CAN 89", table) == "89"


def test_alias_table_has_reasons() -> None:
    rows = identity._rows("aliases.csv")
    assert rows and all(r["reason"] for r in rows)


def test_person_tidy_and_nickname() -> None:
    assert identity.person("  JOHN  SMITH ") == "John Smith"
    assert identity.person("Buckey") == "Lenny Rezabek"


def test_verify_accepts_unbroken_ties_only() -> None:
    from j105.verify import check_event

    def ev(places_nets: list[tuple[int, float]]) -> dict:
        rs = [dict(res(str(i), n), place=p) for i, (p, n) in enumerate(places_nets, 1)]
        return {"fleet": len(rs), "results": rs, "scored": True, "url": "u"}

    assert check_event(ev([(1, 3), (2, 5), (2, 5), (4, 9)])) == []
    assert check_event(ev([(1, 3), (2, 5), (2, 6)])) != []


def test_state_codes_and_regions() -> None:
    from j105.regions import region, state_code

    assert state_code("Illinois") == "IL"
    assert state_code("NY NJ") == "NY"
    assert state_code(" Nova Scotia ") == "NS"
    assert region("WA") == "Pacific Northwest"
    assert region("") == ""


def test_clubspot_location_drops_phone_numbers() -> None:
    from j105.sources.clubspot import PHONE

    assert PHONE.sub("", "102 West Strand, Oxford, MD 21654  410.226.5269") == (
        "102 West Strand, Oxford, MD 21654"
    )


def test_event_state_from_source_or_host_table() -> None:
    from j105.regions import event_state, host_key

    assert host_key("Hosted by The Houston Yacht Club") == "houston yacht club"
    ev = {"source": "regattanetwork", "event_id": "0", "state": "", "host": "TRED AVON YACHT CLUB"}
    assert event_state(ev) == "MD"
    assert event_state({**ev, "state": "Virginia"}) == "VA"  # the source's own state wins
    # Generic name pinned per event: this Corinthian YC event is in San Francisco, not MA.
    assert event_state({**ev, "event_id": "16428", "host": "Corinthian Yacht Club"}) == "CA"
    assert event_state({**ev, "host": "Corinthian Yacht Club"}) == "MA"
    # Proposed rows (here an organizer with no state) are not applied.
    assert event_state({**ev, "host": "Sailing World"}) == ""


def test_host_table_rows_are_complete() -> None:
    from j105.regions import APPLIED

    rows = identity._rows("host_clubs.csv")
    assert rows and all(r["note"] for r in rows)
    assert all(r["state"] for r in rows if r["status"] in APPLIED)
    assert {r["status"] for r in rows} <= APPLIED | {"proposed"}
