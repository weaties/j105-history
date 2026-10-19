"""j105.org archive parser, against small synthetic pages in the archive's formats."""

from j105.sources import j105org


def parse(body: str, year: int = 2004) -> list[dict]:
    return j105org.parse_page(f"<html><body>{body}</body></html>", year)  # type: ignore[return-value]


def test_pre_block_with_header_and_tie() -> None:
    (e,) = parse(
        """<h3>Test Regatta (June 1-2), Annapolis, MD</h3>
<pre>
 Pl  Sail # Skipper               Boat Name    1   2   3   T
 1   145    Strauss               Heart Throb  1   1   1   3
 2   50754  Hill/ Lowden          Dark Horse   2   3   2   7
 2   102    Hardy                 Jaguar       3   2   2   7
</pre>""",
        2002,
    )
    assert (e["start"], e["end"], e["state"], e["fleet"]) == ("2002-06-01", "2002-06-02", "MD", 3)
    rows = [(r["place"], r["sail"], r["boat"], r["skipper"], r["net"]) for r in e["results"]]
    assert rows == [
        (1, "145", "Heart Throb", "Strauss", 3.0),
        (2, "50754", "Dark Horse", "Hill/ Lowden", 7.0),
        (2, "102", "Jaguar", "Hardy", 7.0),
    ]


def test_br_lines_caps_boat_and_last_first_skipper() -> None:
    (e,) = parse(
        "<h2>Galveston NOOD <br> September 24-26, 2004</h2>"
        "Sail Boat Skipper R1 R2 R3 T <br>"
        "1 629 GRINGO Glaze,Ryan 2 2 3 7 <br>"
        "2 344 SHOCK &amp; AWE Brann,Robert 1 3 9 13 <br>"
    )
    assert e["name"] == "Galveston NOOD" and e["state"] == "TX"
    assert [(r["sail"], r["boat"], r["skipper"], r["net"]) for r in e["results"]] == [
        ("629", "GRINGO", "Glaze,Ryan", 7.0),
        ("344", "SHOCK & AWE", "Brann,Robert", 13.0),
    ]


def test_table_with_header_keeps_only_the_j105_class() -> None:
    def tr(*cells: str) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    header = tr("Place", "#", "Boat Name", "Owner", "R 1", "R 2", "Total")
    events = parse(
        "<h2>Chicago NOOD June 15-17, 2007</h2><table>"
        + tr("J/35", "")
        + header
        + tr("1", "99", "Other Boat", "Someone Else", "1", "1", "2")
        + tr("J/105", "back to top")
        + header
        + tr("1", "288", "Messy Jessy", "Dorin Candea", "1", "(3)", "1")
        + tr("2", "USA 46", "Lucky Dubie", "Len Siegal", "2", "1", "3")
        + "</table>",
        2007,
    )
    (e,) = events
    assert e["class"] == "J/105" and e["fleet"] == 2
    assert [(r["sail"], r["boat"], r["net"]) for r in e["results"]] == [
        ("288", "Messy Jessy", 1.0),
        ("46", "Lucky Dubie", 3.0),
    ]


def test_missing_sail_and_home_port_line() -> None:
    (e,) = parse(
        """<h2>September 1996</h2>
<h3>1996 North Americans (September 20-22), Annapolis, MD</h3>
<pre>
 1  Bo Robinson         Squeeze Play      (7)  2   1   1   2   1     6.25
    Annapolis, MD
 2  Robert Taylor       XSNRJ              2   3   2   2  (6)  3    12.00
    Newport, RI
</pre>""",
        1996,
    )
    assert e["start"] == "1996-09-20" and e["state"] == "MD"
    r1, r2 = e["results"]
    assert (r1["sail"], r1["boat"], r1["skipper"], r1["home"], r1["net"]) == (
        "",
        "Squeeze Play",
        "Bo Robinson",
        "Annapolis, MD",
        6.25,
    )
    assert (r2["boat"], r2["skipper"], r2["place"]) == ("XSNRJ", "Robert Taylor", 2)


def test_sail_first_rows_with_place_last() -> None:
    (e,) = parse(
        """<h3>Key West Race Week January 18-22, 1999</h3>
<pre>
43955  Phenix            Bob Swirbalus      3    2    7    23     1
35     Hi-Jinx           Tom Thayer         1    5    6    26     2
</pre>""",
        1999,
    )
    assert [(r["place"], r["sail"], r["net"]) for r in e["results"]] == [
        (1, "43955", 23.0),
        (2, "35", 26.0),
    ]


def test_implausible_blocks_are_dropped_not_stored() -> None:
    events = parse(
        """<h3>Monday morning quarterbacking</h3>
<pre>
3. Crew. As you might expect it is not always the same group of people aboard, 1 2 3 4
7. Instrumentation. He sails without any instruments at all, 5 6 7 8
</pre>"""
    )
    assert events == []


def _tr(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def test_bow_sail_column_keeps_the_sail() -> None:
    (e,) = parse(
        "<h2>North American Championship, Annapolis, MD November 1-4, 2007</h2><table>"
        + _tr("Pos", "Bow/Sail", "Boat", "Skipper", "1", "2", "Total Points", "Pos")
        + _tr("1", "68/ 328", "Mirage", "Cedric Lewis", "1", "2", "3.00", "1")
        + _tr("2", "29/ USA 29", "Convexity", "Donald Wilson", "2", "1", "3.00", "2")
        + "</table>",
        2007,
    )
    assert [(r["sail"], r["sail_country"]) for r in e["results"]] == [("328", ""), ("29", "USA")]


def test_hash_column_of_bow_numbers_becomes_unknown_sail() -> None:
    header = _tr("Place", "#", "Boat Name", "Owner", "R 1", "R 2", "Total")
    sails = parse(  # an event that prints the real sail numbers
        "<h2>Annapolis NOOD April 28-30, 2006</h2><table>"
        + _tr("Pos", "Sail", "Boat", "Skipper", "1", "2", "Total Points")
        + _tr("1", "17", "Masquerade", "Thomas Coates", "1", "1", "2")
        + _tr("2", "281", "Flame", "James Doane", "2", "2", "4")
        + "</table>",
        2006,
    )
    bows = parse(
        "<h2>Key West Race Week January 17-21, 2005</h2><table>"
        + header
        + _tr("1", "64", "Masquerade", "Thomas Coates", "1", "1", "2")
        + _tr("2", "75", "Flame", "James Doane", "2", "2", "4")
        + _tr("3", "80", "USA 332", "Jim Johnstone", "3", "3", "6")
        + "</table>",
        2005,
    )
    real = parse(  # "#" holding real sails, as at most NOODs, is kept
        "<h2>Chicago NOOD June 15-17, 2007</h2><table>"
        + header
        + _tr("1", "17", "Masquerade", "Thomas Coates", "1", "1", "2")
        + _tr("2", "059", "Gumption 3", "Kevin Grainger", "2", "2", "4")
        + "</table>",
        2007,
    )
    events = sails + bows + real
    assert j105org.resolve_bow_numbers(events) == ["2005-key-west-race-week/j-105"]
    kw = events[1]["results"]
    # Bow numbers dropped; "USA 332" printed in the boat column is that boat's sail.
    assert [(r["sail"], r["boat"]) for r in kw] == [
        ("", "Masquerade"),
        ("", "Flame"),
        ("332", "USA 332"),
    ]
    assert [r["sail"] for r in events[2]["results"]] == ["17", "59"]
    assert not any("_hash" in r for e in events for r in e["results"])


def test_country_sail_beats_a_bow_number_in_unlabelled_rows() -> None:
    (e,) = parse(
        "<h2>Charleston Race Week April 17-20, 2008</h2><table>"
        + _tr(
            "",
            "",
            "1.",
            "30",
            "USA 658",
            "Big Booty",
            "Patrick Eudy",
            "",
            "6",
            "1",
            "[6]",
            "",
            "7.0",
        )
        + _tr(
            "",
            "",
            "2.",
            "33",
            "USA 90",
            "Max Power",
            "Gerrit Schulze",
            "",
            "1",
            "2",
            "[2]",
            "",
            "9.0",
        )
        + "</table>",
        2008,
    )
    assert [(r["sail"], r["sail_country"], r["boat"], r["skipper"]) for r in e["results"]] == [
        ("658", "USA", "Big Booty", "Patrick Eudy"),
        ("90", "USA", "Max Power", "Gerrit Schulze"),
    ]


def test_boat_named_like_a_sail_number_is_kept() -> None:
    (e,) = parse(
        "<h2>Chicago NOOD June 15-17, 2001</h2>"
        "<pre>\n 1  46     LUCKY DUBIE    Siegal          1  1   2\n"
        " 2  370    USA 370        Petkovic        2  2   4\n</pre>",
        2001,
    )
    assert [(r["sail"], r["boat"], r["skipper"]) for r in e["results"]][1] == (
        "370",
        "USA 370",
        "Petkovic",
    )


def test_race_scores_with_discards_codes_and_a_discard_column() -> None:
    (table,) = parse(
        "<h2>Key West Race Week January 17-21, 2005</h2><table>"
        + _tr("Place", "Sail", "Boat Name", "Owner", "R 1", "R 2", "R 3", "R 4", "Total")
        + _tr("1", "17", "Masquerade", "Thomas Coates", "1", "- 9", "(3)", ".75", "1.75")
        + _tr("2", "281", "Flame", "James Doane", "2", "8 DSQ", "1", "", "11")
        + "</table>",
        2005,
    )
    first, second = table["results"]
    assert first["race_scores"] == [
        [1.0, "", False], [9.0, "", True], [3.0, "", True], [0.75, "", False],
    ]  # fmt: skip
    assert second["race_scores"] == [[2.0, "", False], [8.0, "DSQ", False], [1.0, "", False]]
    for r in (first, second):
        kept = sum(p for p, _, dropped in r["race_scores"] if p is not None and not dropped)
        assert kept == r["net"]
    # Unlabelled rows ending "[13] | | 21.0": the bracketed cell repeats the discarded race.
    (rows,) = parse(
        "<h2>Block Island Race Week June 18-22, 2007</h2><table>"
        + _tr(
            "",
            "",
            "1.",
            "USA 526",
            "Savasana",
            "Brian Keane",
            "",
            "1",
            "13",
            "7",
            "[13]",
            "",
            "8.0",
        )
        + _tr(
            "", "", "2.", "USA 324", "Kincsem", "Joerg Esdorn", "", "6", "7", "3", "[7]", "", "9.0"
        )
        + "</table>",
        2007,
    )
    assert rows["results"][0]["race_scores"] == [
        [1.0, "", False],
        [13.0, "", True],
        [7.0, "", False],
    ]
    assert rows["results"][1]["race_scores"] == [
        [6.0, "", False],
        [7.0, "", True],
        [3.0, "", False],
    ]
