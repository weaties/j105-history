from j105.sources.styc import parse_page
from j105.verify import check_event

HEAD = (
    "<tr><th>Boat Name</th><th>SailNo</th><th>Boat Type</th><th>Skipper</th><th>Rating</th>"
    "<th>Club</th>{cols}<th>Place</th></tr>"
)


def row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


SERIES = f"""<h1>2019 Ballard Cup Series I<br></h1>
<a href=race1.htm>R1</a> <a href=race2.htm>R2</a>
<h3>Class 7 - Flying Sails Division</h3>
<table>{HEAD.format(cols="<th>Race 1</th><th>Race 2</th><th>Total</th>")}
{row("Corvo 105", "475", "J105", "Tom Kerr", "93", "STYC", "1", "1", "2", "1")}
{row("Creative", "51911 &#40;Or 422&#41;", "J/105", "Al Hughes", "93", "SC", "2", "(3)", "5", "2")}
</table>"""

RACE = f"""<p class=racetitle>2025 Fall Regatta</p><p class=racedate>Nov 1, 2025</p>
Class: 5 - Flying Sails Division - Start: 14:20:00 - Course: X
<table>{HEAD.format(cols="<th>Start</th><th>Finish</th>")}
{row("Valkyrie", "1", "Express 37", "A", "90", "STYC", "14:20:00", "15:01:02", "1")}
{row("Panic", "482", "J105", "Mike Cain", "93", "STYC", "14:20:00", "15:02:00", "2")}
{row("Moonglow", "525", "J/105", "B", "93", "SSC", "14:20:00", "15:03:00", "3")}
{row("Paladin", "412", "J105", "Drew Zangle", "93", "CYC", "14:20:00", "15:03:00", "3")}
</table>"""

UNSAILED = RACE.replace("15:0", "DNC").replace("<td>DNC1:02</td>", "<td>DNC</td>")


def meta(url: str) -> dict:
    return {"race": "x", "year": 2025, "url": "https://race.styc.org/race_info/" + url}


def test_series_one_design() -> None:
    [e] = parse_page(SERIES, meta("Ballard_Cup/SeriesI/2019/series.htm"))
    assert e["class"] == "Class 7 - Flying Sails Division" and e["races"] == 2
    assert not e.get("mixed") and e["scored"]
    assert [(r["sail"], r["net"], r["place"]) for r in e["results"]] == [
        ("475", 2.0, 1),
        ("51911", 5.0, 2),
    ]
    assert check_event(e) == []


def test_race_mixed_with_tie() -> None:
    [e] = parse_page(RACE, meta("Fall Regatta/2025/race1.htm"))
    assert e["mixed"] and e["division_size"] == 4 and e["fleet"] == 3
    assert e["start"] == "2025-11-01" and e["class_id"] == "5" and e["races"] == 1
    assert [(r["boat"], r["place"]) for r in e["results"]] == [
        ("Panic", 1),
        ("Moonglow", 2),
        ("Paladin", 2),
    ]
    assert check_event(e) == []


def test_unsailed_race_is_not_scored() -> None:
    [e] = parse_page(UNSAILED, meta("Fall Regatta/2025/race1.htm"))
    assert not e["scored"]
