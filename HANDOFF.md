# Handoff prompt — paste everything below the line into a new Claude Code session started in `~/src/j105-history`

---

You are picking up a project in `~/src/j105-history`: a **North American J/105 results database and website**, keyed by sail number, that the J/105 Class Association and any skipper or crew can use for analysis. Both the published page (a claude.ai artifact) and all source code and data will be shared with the class, so everything you build must be reproducible from this repo by someone else.

## Your first job: set up the project for the long haul

1. Read this whole prompt, then `ls -R collect site data/raw | head -100` to see what exists.
2. Create **`CLAUDE.md`** at the repo root. Put the durable project knowledge from this prompt there: purpose, sources and their APIs and quirks, data schema, identity rules, privacy rules, scoring and metrics definitions, and the conventions below. Keep it concise and skimmable; put long procedures into skills instead.
3. Create project skills under **`.claude/skills/<name>/SKILL.md`** (YAML front matter `name` and `description`, then instructions):
   - **`collect`**: run or resume the collectors for one source or all of them. Be polite to every server (at most 4 concurrent requests, retries with backoff, a browser User-Agent), cache raw responses under `data/raw/`, and make every collector resumable and idempotent.
   - **`add-source`**: the checklist for adding a new scoring system: discovery, a standings collector in the common schema, verification against the official totals, attribution and link back, and a terms-of-use check.
   - **`identity`**: resolve sail numbers to hulls, review the alias table, and detect renames and new skippers. Flag ambiguous cases for a human instead of merging them silently.
   - **`verify`**: compare rebuilt standings with each event's official totals and places. Report mismatches; never "fix" data to match without a recorded reason.
   - **`publish`**: build the site data and publish or update the artifact. Explain the artifact rules (see below).
   - **`privacy`**: what personal data may be stored and published, and how to handle a removal request.
4. Turn the repo into a proper standalone project. Use `uv` with Python 3.12, `ruff` (line length 100) and `pytest`. Add a `README.md` for the class: what it is, how to run it, how to add results, how to request a correction or removal. Add `LICENSE` (suggest MIT for code; data is derived from public results, attributed per source). Add `CONTRIBUTING.md` and a `.gitignore` (cache folders such as `data/raw/rn_pages/` may be large, so decide what gets committed).
5. **Do not push to GitHub or make anything public without asking.** The user will decide where the repo lives and when to share it.

## Background: how we got here

The work started in the HelmLog project (the user's boat logger, `~/src/helmlog`; their boat is Corvo 105, sail 475, Puget Sound). It produced four published artifacts, which are references for style and behaviour. **Don't overwrite them**; publish the class-wide site as a new artifact.
- 2026 J/105 NAs standings: https://claude.ai/artifact/GofSJDqxCQ9e8vfHjGkT5i (local copy `site/reference/na-standings.html`)
- Puget Sound Monday/Wednesday series 2025–26: https://claude.ai/artifact/N12WikU9nBzwzrcWptmXhg (`site/reference/series-mw.html`)
- Race Week 2025–26: https://claude.ai/artifact/QAndZxnC8R2mmYTomEyiw7 (`site/reference/race-week.html`)
- Puget Sound J/105 fleet history 2012–26: https://claude.ai/artifact/NJKANqPSxN7gVYqD3yzHkv (`site/reference/history.html`). This is the prototype to generalise to all of North America.

`collect/legacy/` holds the Puget Sound-era scripts and templates. Some import `helmlog` or use paths in a temporary scratch folder; treat them as reference and port what you need into standalone code. `data/raw/puget_sound/` holds that era's verified data.

## Current state of the North America collection (at handoff)

| Source | Discovery | Standings | Status |
|---|---|---|---|
| Clubspot | `collect/discover_clubspot.py` → `data/raw/clubspot_index.json`: 250 J/105 classes in 244 regattas | `collect/clubspot_all.py` → `data/raw/clubspot_events.json` | **Done**: 153 scored events, 1,770 boat results, 226 sail numbers, 2019–2026 |
| Yacht Scoring | `collect/discover_ys.py` scans all ~7,450 events' `/splits` → `data/raw/ys_index.json` | `collect/ys_all.py` (written, **not yet run**) → `data/raw/ys_events.json` | The scan was running at handoff, finding about 10% of events with J/105 (~700 expected). If `ys_index.json` is missing or short, rerun discovery (it isn't resumable yet; make it so). |
| Regatta Network | `collect/discover_rn.py`: year lists 2008–2026, then every results page; J/105 pages saved to `data/raw/rn_pages/<id>.html` and indexed in `data/raw/rn_index.json` | **No parser yet** | The scan was running at handoff, with pages cached as they're found, so a rerun skips cached ones. Write the standings parser. |
| STYC (Seattle) | known URLs | `collect/legacy/styc.py` | Ballard Cup 2014–2026 done for Puget Sound; STYC also hosts other series |
| j105.org archive | `https://archive.j105.org/j105results{1996..2008}.html` | none | Hand-made HTML tables, several formats per page (Pl, Sail #, Skipper, Boat, race scores, T). Valuable for 1996–2008 history. |
| Jibeset (SF Bay) | `https://www.jibeset.net/regattaall.php` (current year only); per club `ourregatta.php?A00=yes&A11=yes&CLUB=<code>` | none | The SF J/105 fleet (Fleet 1, the largest) mostly scores on Clubspot now; Jibeset may hold older YRA and club results. |
| Sailwave pages | ad hoc, e.g. `https://www.sailwave.com/results/AnacortesRaceWeek2022.htm` | none | Found through web search |

Other leads not yet explored: regional fleet websites (Chesapeake, Great Lakes, Texas, Toronto/Lake Ontario, Nova Scotia, SF), CYC Seattle results before 2024, Regatta Network's Anacortes Yacht Club events.

## Source APIs and quirks (verified)

**Clubspot** (Parse backend)
- `GET https://theclubspot.com/parse/classes/<Class>?where=<json>&keys=..&limit=..&skip=..` with header `X-Parse-Application-Id: myclubspot2017`.
- Find J/105 classes: `boatClasses` where `name` matches the regex `(?i)j\s*/?\s*-?\s*105`; each has `regattaObject.objectId`.
- `regattas/<id>` has `name`, `startDate.iso`, `endDate.iso`, `location`, `city`, `state`, `country` and `clubObject`, which points at `clubs/<id>` for the host club's `name`.
- Results: `GET https://results.theclubspot.com/clubspot-results-v4/<regattaId>?boatClassIDs=<classId>` returns `scoresByRegistration[]`. Each entry has:
  - `registrationObject`: `boatName`, `sailNumber`, `sailNumber_country`, `firstName`, `lastName`, `clubName`.
  - `scoring_data[]`: `race_number`, `points`, `letterScore`, `throwout`, `start_data.start_time`.
  - `total` and `net`.
- There's no place field: rank by `net`, then `total` (tiebreaks aren't exposed, so ties can come out in the wrong order).
- Throwout counts don't follow the published schedule; use the `throwout` flags.
- Test and "CLONED" regattas exist; skip them.
- Some regattas split one season into many sub-regattas (CYC Seattle 2024).

**Yacht Scoring** (`https://api.yachtscoring.com/v1/public/event`; send a browser User-Agent)
- List events with `?size=500&page=N` (~7,450 events, back to 2009).
- `/<id>` has `name`, `startDate`, `endDate`, `city`, `state`, `country`, `eventRegion` and `hostClub.name`.
- `/<id>/splits` lists classes: `splitClassName`, `splitClass`.
- `/<id>/cumulative-result` holds class blocks with `className` and `boats[]`:
  - each boat has `sailPrefix`, `sailNumber`, `name`, `owner{firstName,lastName,city,state}`, `raceTotal` (net), `throwOut1..7`, `records[]`, and `eventBoatId`, which joins to `/boats` `id`.
  - Boats are already in finishing order.
- `/<id>/boats?size=&page=` gives `year` (build year), `boatId` (a Yacht Scoring id that stays the same across events, useful for identity) and `owner{..., club}`. It also contains US Sailing numbers, a World Sailing classification and `crewNames`: **do not store those**.
- HelmLog's old provider failed on some events (2024 Race Week Anacortes, id 16303). `cumulative-result` worked, which is why `ys_all.py` uses it.
- The old `.cfm` result pages are now a JavaScript app.

**Regatta Network**
- Year list: `https://www.regattanetwork.com/html/results.php?year=YYYY` (2008 onward). Results: `https://www.regattanetwork.com/clubmgmt/applet_regatta_results.php?regatta_id=N`.
- Each division block has a heading like `<Division> (N boats)`, then columns `Pos | Sail | Boat | Rating | Skipper | Yacht Club | race cells … | Total`.
- J/105s may be their own division or mixed into PHRF. If mixed, rank only the J/105s, and say so.

**STYC** (`https://race.styc.org/race_info/Ballard_Cup/Series{I,II,III}/{year}/series.htm`, 2014 onward)
- One table per class, with `Boat Name | SailNo | Boat Type | Skipper | Rating | Club | Race n… | Total | Place`.
- Throwouts are shown in parentheses, and codes appear as e.g. `12 DNC`.
- Only Series III was sailed in 2020.

## Common event schema (`data/raw/*_events.json`)

```
{source, event_id, class_id, class, name, start, end, city, state, country, region?, location?, host,
 url (official results page), fleet, races, scored, results: [
   {sail, sail_country, boat, skipper, club, home?, built?, ys_boat?, net, total?, place, races_sailed?} ]}
```
Keep the official results URL on every event and link to it from the site.

## Identity rules (hull = sail number)

- J/105 sail numbers are normally the hull number and unique across the US and Canada. The key is the sail number's digits with leading zeros stripped; `sail_country` varies (Moose Unknown #89 appears as both USA and CAN).
- Known typos and renumbers merged in the Puget Sound work: Creative 51911 = 686 = 422 = 422229; LiftOff 403 = 404; Cyrano 253 = 255 = 258. Some boats race under PHRF numbers instead of hull numbers (51911, 33406). Keep an explicit alias table with a reason for each entry.
- Use Yacht Scoring's `boatId` and name and skipper continuity as evidence. When a number seems to belong to two hulls (e.g. Kinetic #401 in SF vs Kinetic #440 in Seattle — different boats), keep them separate.
- **Ownership is inferred, never asserted.** Mark a rename when the boat's most common name changes from one year to the next. Mark a new "skipper of record" (the year's most frequent skipper) only if that skipper is still the skipper of record the following season. Use a nickname table, e.g. "Buckey" = Lenny Rezabek.
- Club and shared boats (e.g. Puff, Seattle Sailing Club) change skipper constantly. Label them; don't count each change as an ownership change.

## Metrics

- Event score = share of the fleet beaten: `(fleet − place) / (fleet − 1)`.
- Season score = the mean over the events a boat sailed that year.
- Always show places and fleet size next to scores.
- Before 2018, Puget Sound J/105s often raced in mixed PHRF classes. Rank them among J/105s only, and say so.
- Region or home fleet: infer from event location (state/province) and the boat's most frequent venue. The J/105 class has numbered fleets (e.g. Fleet 1 = San Francisco); add a table mapping regions to fleets.

## Privacy and redistribution rules

- Store only what public results already publish and the analysis needs: boat name, sail number, skipper or owner name as printed, home club, home city/state when the scorer shows it, and build year.
- **Never store** US Sailing or World Sailing numbers or classifications, emails, phone numbers, or crew lists.
- Add a way to remove or correct a person's name (an opt-out list applied at build time), document it in the README, and honour requests quickly.
- Check each source's terms of use before redistributing raw data. Prefer publishing derived standings with attribution and links over republishing raw pages; `.gitignore` large raw caches if their terms are unclear.

## Site and artifact (publish rules learned the hard way)

- Build a new artifact, not one of the four above. It starts private; the user shares it from its Share menu.
- One HTML page with supporting data files published alongside it (the `files` parameter) and fetched by relative URL. Keep each file under 16 MB; split by year or source if needed.
- External scripts load only from cdnjs, jsDelivr or unpkg, pinned to an exact version. Only Google Fonts for stylesheets. No `window.print()`, alerts or iframes.
- Deep links use only `#token` (letters, digits, `. _ ~ -`), e.g. `#hull-475`, `#season-2025`, `#bc~corvo-105`. Query strings don't reach the page.
- Reuse the reference pages' look:
  - tokens on `:root` with dark-mode overrides (`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, plus `:root[data-theme="dark"]`);
  - fonts Barlow Condensed (display), IBM Plex Sans (body) and IBM Plex Mono (numbers);
  - a 16px side gutter written as `max(16px, env(safe-area-inset-left))`;
  - wide tables scroll inside their own container.
- **Don't feature any one boat.** No default highlight; the reader picks boats, and the first pick is the baseline.
- Planned views:
  - **Search:** sail number, boat, skipper, club.
  - **Hull profile:** names and skippers by year, every result linked to the official page, trend by event type, renames and new skippers.
  - **Events:** filter by year, region, host club and source.
  - **Season or region rankings:** with a minimum-events filter.
  - **Class participation over time:** boats per year per region.
  - **Data coverage:** which sources and years are included and what's missing.
- Before publishing, verify the numbers: for each source, spot-check events against the official site (places, fleet size, net totals).

## Conventions

- Work in small, verifiable steps; after each collector run, print counts per year and per region.
- Commit with clear messages; ask before any push. Don't commit secrets.
- When you're unsure whether two records are the same boat or person, leave them separate and list the question for the user.

Start by doing the setup (CLAUDE.md, skills, project scaffolding). Then check whether `data/raw/ys_index.json` and `data/raw/rn_index.json` are complete, run `collect/ys_all.py`, write the Regatta Network parser, and report counts before building the site.
