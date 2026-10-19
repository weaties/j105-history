"""Regatta Network parser, against a small synthetic page that mimics the real markup."""

from j105.sources.regattanetwork import _clean_sail, _date, parse_page

ROW = """<tr><td>{pos}</td><td>{sail}</td><td>{boat}</td><td>{skipper}</td><td>{club}</td>
<td bgcolor="#999999"></td><td>{r1}</td><td>{r2}</td><td bgcolor="#999999"></td>
<td>{total}</td><td class="pos">{pos}</td></tr>"""
HEADER = """<tr><thead><tr><td class="pos">Pos</td><td>Sail&nbsp;</td><td>Boat</td><td>Skipper</td>
<td>Yacht Club</td><td></td><td>1</td><td>2</td><td></td><td>Total</td><td>Pos</td></tr>"""


def division(name: str, n: int, races: int, rows: list[dict[str, str]]) -> str:
    body = "".join(ROW.format(**r) for r in rows)
    return f"""<h2><a href="#" name="{name}">{name}</a> ( <small>{n}</small> boats)
    Series Standing - {races} races scored</h2>
    <table class="scoring-table">{HEADER}{body}</table>"""


def page(*divisions: str) -> str:
    return f"""<html><head><title>Spring Regatta - Series Standing</title></head>
    <body>Spring Regatta Example Yacht Club | [ View in Media Format ] {"".join(divisions)}
    </body></html>"""


def r(pos: int, sail: str, boat: str, skipper: str, total: str) -> dict[str, str]:
    return dict(pos=str(pos), sail=sail, boat=boat, skipper=skipper, club="EYC",
                r1="1", r2="2", total=total)  # fmt: skip


META = {"id": "123", "year": 2024, "title": "05/18/24 Spring Regatta Example Yacht Club"}


def test_pure_division() -> None:
    html = page(
        division(
            "J/105",
            2,
            2,
            [r(1, "USA 475", "Corvo 105", "A Sailor", "3"), r(2, "89", "Moose", "B", "5")],
        )
    )
    [ev] = parse_page(html, META)
    assert ev["class"] == "J/105"
    assert ev["start"] == "2024-05-18"
    assert ev["host"] == "Example Yacht Club"
    assert ev["fleet"] == 2 and ev["races"] == 2 and ev["scored"]
    assert "mixed" not in ev
    assert [(x["sail"], x["sail_country"], x["place"], x["net"]) for x in ev["results"]] == [
        ("475", "USA", 1, 3.0),
        ("89", "", 2, 5.0),
    ]
    assert ev["url"].endswith("regatta_id=123")


def test_mixed_division_keeps_flagged_boats_and_reranks() -> None:
    rows = [
        r(1, "40", "Fast 40", "X", "2"),
        r(2, "9/J105", "Skookum", "Y", "4"),
        r(3, "33", "Other", "Z", "6"),
        r(4, "253", "Cyrano", "Bo Smith [1B][J105]", "8"),
    ]
    [ev] = parse_page(page(division("PHRF A", 4, 2, rows)), META)
    assert ev["mixed"] is True and ev["division_size"] == 4
    assert [(x["sail"], x["skipper"], x["place"]) for x in ev["results"]] == [
        ("9", "Y", 1),
        ("253", "Bo Smith", 2),
    ]


def test_unscored_division_is_not_scored() -> None:
    [ev] = parse_page(page(division("J105", 1, 0, [r(1, "475", "Corvo", "A", "0")])), META)
    assert not ev["scored"]


def test_mixed_class_name_without_flags_is_skipped() -> None:
    html = page(
        division("J/105 and J/88", 2, 2, [r(1, "1", "A", "A", "2"), r(2, "2", "B", "B", "4")])
    )
    assert parse_page(html, META) == []


def test_helpers() -> None:
    assert _date("10/27/07 Great Pumpkin") == "2007-10-27"
    assert _date("no date") == ""
    assert _clean_sail("USA-519") == ("519", "USA")
    assert _clean_sail("12 / 519") == ("519", "")
