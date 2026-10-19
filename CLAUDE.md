# CLAUDE.md — J/105 History

A **North American J/105 results database and website**, keyed by sail number (= hull), for the
J/105 Class Association and any skipper or crew. Code, data and the published page are shared
with the class, so everything must be reproducible from this repo by someone else.

**Never push to GitHub or make anything public without asking the user.** Commit locally with
clear messages; no secrets.

## Commands

```bash
uv sync                              # install
uv run j105 discover <source|all>    # find events with a J/105 class (resumable, cached)
uv run j105 collect <source|all>     # standings -> data/raw/<src>_events.json, then counts
uv run j105 counts [source]          # events / boat results per year and region
uv run j105 verify                   # consistency checks + random events to spot-check by hand
uv run pytest && uv run ruff check . && uv run ruff format --check .
```

Sources: `clubspot`, `yachtscoring`, `regattanetwork`. Skills in `.claude/skills/`: `collect`,
`add-source`, `identity`, `verify`, `publish`, `privacy`.

## Layout

- `src/j105/http.py` — the only way to fetch: browser User-Agent, ≤4 requests in flight,
  retries with backoff, raw replies cached in `data/raw/cache/<source>/` (git-ignored).
- `src/j105/sources/<source>.py` — `discover()` and `standings()` per scoring system.
- `src/j105/schema.py` (common event schema), `identity.py` (hulls, names, opt-outs),
  `regions.py` (state codes → regions), `verify.py`, `cli.py`.
- `data/raw/*_index.json` (discovery) and `*_events.json` (standings) are committed outputs.
- `data/identity/*.csv` — human-reviewed tables: `aliases`, `nicknames`, `shared_boats`, `optout`.
- `data/raw/puget_sound/` — verified Puget Sound-era data. `collect/legacy/` — Puget Sound
  scripts, reference only (some import `helmlog`); port code out, don't edit. Not linted.
- `site/reference/` — local copies of four earlier artifacts (style reference; see `publish`).

## Sources (status and quirks: see the `collect` and `add-source` skills for detail)

| Source | Coverage | Notes |
|---|---|---|
| Clubspot | 2019– | No place field: rank by net, then total (tiebreaks hidden). Skip test/"CLONED". |
| Yacht Scoring | 2006– | `cumulative-result` boats are in official order; `/boats` adds club, build year, `boatId`. |
| Regatta Network | 2006– | HTML; no city/state (infer from host club). J/105s can be mixed into PHRF. |
| STYC, j105.org archive (1996–2008), Jibeset, Sailwave | — | Not yet collected. |

Unscored events (0 races, cancelled, entry list only) are kept with `scored: false`.

## Common event schema (`src/j105/schema.py`)

`{source, event_id, class_id, class, name, start, end, city, state, country, region?, location?,
host, url, fleet, races, scored, mixed?, division_size?, results: [{sail, sail_country, boat,
skipper, club, home?, built?, ys_boat?, net, total?, place, races_sailed?}]}`

- `url` is the official results page: always keep it and link to it from the site.
- `place` is the official place; unbroken ties repeat a place (10, 10, 10).
- `mixed: true` means J/105s raced in a mixed division and were re-ranked among J/105s only;
  `division_size` is the whole division. Always say so on the site.
- The same regatta can appear in more than one source; dedupe at build time, not in collectors.

## Identity rules (hull = sail number)

- Key = sail number digits, leading zeros stripped. `sail_country` varies (Moose Unknown #89 is
  USA and CAN). Aliases (typos, renumbers, PHRF numbers) live in `data/identity/aliases.csv`,
  each with a reason. Evidence: YS `boatId`, boat name and skipper continuity.
- When unsure whether two records are one boat or person, keep them separate and ask the user.
  Same number, different hulls exist (Kinetic #401 SF vs Kinetic #440 Seattle).
- **Ownership is inferred, never asserted.** Rename = the year's most common name changes.
  New "skipper of record" (year's most frequent skipper) only if it holds the next season too.
- Club and shared boats (`shared_boats.csv`) change skipper constantly: not ownership changes.

## Metrics

- Event score = share of fleet beaten: `(fleet − place) / (fleet − 1)`. Season score = mean
  over the boat's events that year. Always show place and fleet size next to scores.
- Mixed-class events (common before 2018 in Puget Sound): rank among J/105s only, and say so.
- Region from event state/province (`regions.py`) and the boat's most frequent venue.

## Privacy (see the `privacy` skill)

Store only what public results publish and the analysis needs: boat name, sail number,
skipper/owner as printed, home club, home city/state if shown, build year. **Never store**
US Sailing / World Sailing numbers or classifications, emails, phones or crew lists. Names in
`optout.csv` are removed or corrected at build time. Don't republish raw pages; publish derived
standings with attribution and links.

## Conventions

- Python 3.12, `uv`, `ruff` (line length 100), `pytest`. Stdlib + BeautifulSoup only so far.
- Collectors are resumable and idempotent: everything goes through the cache; recent events
  are refetched. After each collector run, print counts per year and region.
- Report data mismatches; never "fix" data to match without a recorded reason.
- Small, verifiable steps.
