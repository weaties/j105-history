# J/105 History

A results database for the **North American J/105 class**, keyed by sail number, so that the
J/105 Class Association and any skipper or crew can look up a hull's racing history, compare
boats and seasons, and see how the class has grown region by region.

Results are gathered from public scoring sites, checked against each event's official totals,
and every event links back to its official results page.

## Coverage so far

| Source | Years | Scored J/105 events | Boat results |
|---|---|---|---|
| [Yacht Scoring](https://www.yachtscoring.com) | 2006–2026 | 580 | 6,591 |
| [Regatta Network](https://www.regattanetwork.com) | 2006–2026 | 436 | 3,420 |
| [Clubspot](https://www.theclubspot.com) | 2019–2026 | 153 | 1,770 |

Not yet included: the j105.org archive (1996–2008), STYC series, Jibeset and Sailwave pages,
and regional fleet websites. Help finding results is welcome (see below).

## Running it

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed automatically).

```bash
uv sync
uv run j105 discover all     # find events with a J/105 class (slow the first time)
uv run j105 collect all      # standings -> data/raw/<source>_events.json
uv run j105 counts           # events and boat results per year and region
uv run j105 verify           # consistency checks and events to spot-check
uv run pytest
```

Collectors are polite (at most 4 requests at a time, retries with backoff) and resumable:
raw replies are cached in `data/raw/cache/`, which is not committed.

## Adding results

Know a site that scores J/105 events? Open an issue with a link. To add a scoring system
yourself, follow `.claude/skills/add-source/SKILL.md` and see `CONTRIBUTING.md`.

## Corrections and removal

- **Wrong result or wrong boat:** open an issue with the event, the official results link and
  what's wrong. We fix parsers and identity tables; we don't hand-edit results.
- **Two sail numbers that are the same boat (or vice versa):** open an issue with the evidence;
  merges are recorded with a reason in `data/identity/aliases.csv`.
- **Remove or correct your name:** open an issue or contact the maintainers. Your name is added
  to `data/identity/optout.csv` and withheld or corrected on the next build. We act quickly.

## Data and privacy

We keep only what public results publish and the analysis needs: boat name, sail number,
skipper or owner as printed, home club, home city/state when shown, and build year. We never
store membership numbers, sailor classifications, contact details or crew lists.

Ownership and renames are *inferred* from results ("skipper of record"), never asserted.

## License

Code: MIT (see `LICENSE`). Results are derived from public results published by each scoring
site and are credited and linked to their source; check the source's own terms before reusing
them.
