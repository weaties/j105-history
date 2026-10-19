from j105.sources.sailwave import parse_page
from j105.verify import check_event

HEAD = "<tr><th>Rank</th><th>Boat Name</th><th>Boat Type</th><th>SailNo</th><th>Helm</th>"
HEAD += "<th>R1</th><th>R2</th><th>Total</th><th>Nett</th></tr>"


def row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


PAGE = f"""<h1>Race Week</h1><h2>Marina</h2>
<h3 class="summarytitle">J 105 Fleet</h3><table class="summarytable">{HEAD}
{row("1st", "Moose Unknown", "J 105", "Can 89", "A", "1.0", "(3.0)", "4.0", "1.0")}
{row("2nd", "Jaded", "J 105", "USA 299", "B", "2.0", "2.0", "4.0", "4.0")}
</table>
<h3 class="summarytitle">PHRF 2 Fleet</h3><table class="summarytable">{HEAD}
{row("1st", "Vitesse", "Beneteau First 36.7", "USA 240", "C", "1.0", "1.0", "2.0", "2.0")}
{row("2nd", "Panic", "J/105", "USA 482", "D", "2.0", "3.0", "5.0", "5.0")}
{row("3rd", "Elusive", "C&amp;C 115", "USA 51", "E", "3.0", "2.0", "5.0", "5.0")}
{row("4th", "Paladin", "J105", "USA 412", "F", "4.0", "4.0", "8.0", "8.0")}
</table>
<h3 class="racetitle">R1 - J 105 Fleet - June 20, 2022</h3>
<h3 class="racetitle">R2 - J 105 Fleet - June 22, 2022</h3>"""


def test_one_design_and_mixed_fleets() -> None:
    od, mixed = parse_page(PAGE, {"url": "https://www.sailwave.com/results/x.htm", "state": "WA"})
    assert not od.get("mixed") and od["start"] == "2022-06-20" and od["end"] == "2022-06-22"
    assert [(r["sail"], r["sail_country"], r["net"], r["place"]) for r in od["results"]] == [
        ("89", "CAN", 1.0, 1),
        ("299", "USA", 4.0, 2),
    ]
    assert mixed["mixed"] and mixed["division_size"] == 4 and mixed["races"] == 2
    assert [(r["boat"], r["place"]) for r in mixed["results"]] == [("Panic", 1), ("Paladin", 2)]
    assert check_event(od) == [] and check_event(mixed) == []
