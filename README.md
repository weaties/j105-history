# J/105 History

A results database for the **North American J/105 class**, keyed by sail number, so that the
J/105 Class Association and any skipper or crew can look up a hull's racing history, compare
boats and seasons, and see how the class has grown region by region.

Results are gathered from public scoring sites, checked against each event's official totals,
and every event links back to its official results page.

**See the results:** https://claude.ai/artifact/6oLL8NvvMpLP1QhCeUYE8D. Look up any boat by
sail number, name, skipper or club, or browse seasons, events and inactive boats.

## Shared freely

This started as a history of the Puget Sound fleet and grew to cover the whole class. The code,
the collected data and the site are shared freely with the class and anyone else who finds them
useful: use them, copy them, build on them. If you have questions, ideas, corrections or
results we're missing, I'm happy to hear from you. Open an issue on this repository or get in
touch with [@weaties](https://github.com/weaties) (Corvo 105, #475, Puget Sound).

## What's in it

1,722 scored J/105 fleets, 16,679 boat results and 633 sail numbers, 1996–2026:

| Source | Years | Scored fleets | Boat results |
|---|---|---|---|
| [Yacht Scoring](https://www.yachtscoring.com) | 2006–2026 | 914 | 8,459 |
| [Regatta Network](https://www.regattanetwork.com) | 2006–2026 | 432 | 3,398 |
| [Clubspot](https://theclubspot.com) | 2019–2026 | 152 | 1,763 |
| [J/105 Class archive](https://archive.j105.org) | 1996–2008 | 125 | 2,384 |
| [Sloop Tavern YC](https://www.styc.org) (Seattle) | 2015–2026 | 99 | 675 |
| [Sailwave](https://www.sailwave.com) pages | listed by hand | | |

Counts are after merging regattas held by more than one source (each is shown once, with
links to every copy). J/105s that raced in mixed PHRF/ORC classes are included, ranked among
the J/105s only and marked "mixed".

The site (`site/index.html`) has a page per hull (names and skippers by year, every result
with race-by-race scores where they add up), season rankings by region, an events list,
inactive boats (last seen where, and possibly under which number now), and a sources page.

## How it works

```
discover  ->  data/raw/<source>_index.json    which events have J/105s (resumable, cached)
collect   ->  data/raw/<source>_events.json   standings in one common schema, per source
build     ->  site/data/events.json           identity, regions, dedupe, scores (one file)
site/index.html                               reads events.json; no server needed
```

- `src/j105/sources/<source>.py`: one module per scoring system, with `discover()` and
  `standings()`.
- `src/j105/http.py`: the only way to fetch. It's polite (at most 4 requests at a time,
  per-site crawl delays, retries with backoff) and caches raw replies in `data/raw/cache/`
  (not committed).
- `data/identity/*.csv`: human-reviewed tables, applied at build time. Sail-number aliases,
  numbers shared by two boats, results printed without a sail, host club to state, excluded
  events, opt-outs. Every row carries a reason.
- `src/j105/schema.py`: the common event schema. `CLAUDE.md` describes all of it in one place.

## Running it

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed automatically).

```bash
uv sync
uv run j105 discover all     # find events with a J/105 class (slow the first time)
uv run j105 discover yachtscoring --designs   # J/105s in PHRF/ORC classes
uv run j105 collect all      # standings -> data/raw/<source>_events.json
uv run j105 counts           # events and boat results per year and region
uv run j105 build            # site data -> site/data/events.json
uv run j105 hull 475         # one hull's results across all sources
uv run j105 verify           # consistency checks and events to spot-check
uv run pytest
```

The committed `data/raw/*_events.json` files mean you can skip discover and collect and go
straight to `j105 build`. To view the site locally:

```bash
cd site && python3 -m http.server 8000    # then open http://localhost:8000
```

## Expanding it

There's plenty more to find. Here's where to start:

- **Add a Sailwave page.** Add a row to `data/sources/sailwave.csv` (url, city, state, host),
  then `uv run j105 collect sailwave && uv run j105 build`.
- **Add a scoring system or club site.** Write `src/j105/sources/<name>.py` with
  `discover()` and `standings()` returning events in the common schema, register it in
  `src/j105/cli.py` and in `SOURCES` in `src/j105/build.py`, and add parser tests on small
  synthetic pages. Check the site's robots.txt and terms first, and link back to the official
  results. `.claude/skills/add-source/SKILL.md` is the full checklist. `styc.py` and
  `sailwave.py` are short examples.
- **Fix identity.** When two numbers are one boat (a typo or a PHRF number), add a row to
  `data/identity/aliases.csv`. When one number is two boats, add a row to
  `split_numbers.csv`. `uv run j105 identity` lists candidates for review. Rule of thumb:
  when unsure, keep records separate and ask.
- **Map hosts to states.** `uv run j105 hosts` lists events with no state. Add the host club to
  `data/identity/host_clubs.csv`.
- **Improve the site.** It's one HTML file with no build step. Edit `site/index.html` and
  reload.

Gaps worth filling: British Columbia (no source yet), regional fleet websites, older club
archives, Jibeset (SF Bay, whose robots.txt blocks crawlers, so it needs the site's permission),
and a confirmed list of North American Championships.

The repo is set up for [Claude Code](https://claude.com/claude-code). `CLAUDE.md` and the
skills in `.claude/skills/` (`collect`, `add-source`, `identity`, `verify`, `publish`,
`privacy`) hold the project's rules, so an assistant can pick up where the last session left
off.

## Corrections and removal

- **Wrong result or wrong boat:** open an issue with the event, the official results link and
  what's wrong. We fix parsers and identity tables; we don't hand-edit results.
- **Two sail numbers that are the same boat (or vice versa):** open an issue with the evidence.
  Merges are recorded with a reason in `data/identity/aliases.csv`.
- **Remove or correct your name:** open an issue or get in touch. Your name is added to
  `data/identity/optout.csv` and withheld or corrected on the next build. We act quickly.

## Data and privacy

We keep only what public results publish and the analysis needs: boat name, sail number,
skipper or owner as printed, home club, home city/state when shown, and build year. We never
store membership numbers, sailor classifications, contact details or crew lists.

Ownership and renames are *inferred* from results ("skipper of record"), never asserted.

## License

Code: MIT (see `LICENSE`). Results are derived from public results published by each scoring
site and are credited and linked to their source; check the source's own terms before reusing
them.
