---
name: publish
description: Build the site data from the collected standings and publish or update the class-wide J/105 history artifact on claude.ai, following the artifact rules learned on the earlier pages.
---

# Publish the site

## Before building

1. `uv run j105 verify` is clean or every remaining issue is understood, and events have been
   spot-checked against official pages (places, fleet size, net totals) for each source.
2. Apply identity tables (aliases, nicknames) and `optout.csv` at build time — never by
   editing `data/raw/*_events.json`.
3. Dedupe events that appear in more than one source.

## Artifact rules

- **Never overwrite** the four earlier artifacts (local copies in `site/reference/`):
  NAs standings `GofSJDqxCQ9e8vfHjGkT5i`, Puget Sound M/W series `N12WikU9nBzwzrcWptmXhg`,
  Race Week `QAndZxnC8R2mmYTomEyiw7`, Puget Sound history `NJKANqPSxN7gVYqD3yzHkv` (the prototype
  to generalise). Publish the class-wide site as a **new** artifact; record its URL in
  `CLAUDE.md` and update it in place afterwards.
- Artifacts start private; the user shares from the Share menu. Ask before sharing anything.
- One HTML page plus data files published alongside it (`files`), fetched by relative URL.
  Each file < 16 MB; split by year or source if needed.
- External scripts only from cdnjs, jsDelivr or unpkg, pinned to an exact version; stylesheets
  only from Google Fonts. No `window.print()`, alerts or iframes.
- Deep links only as `#token` (letters, digits, `. _ ~ -`): `#hull-475`, `#season-2025`,
  `#bc~corvo-105`. Query strings don't reach the page.
- Look of the reference pages: colour tokens on `:root` with dark mode under
  `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, plus
  `:root[data-theme="dark"]`; Barlow Condensed (display), IBM Plex Sans (body), IBM Plex Mono
  (numbers); side gutter `max(16px, env(safe-area-inset-left))`; wide tables scroll in their
  own container.
- **Don't feature any one boat.** No default highlight; the reader picks boats, first pick is
  the baseline.

## Views

Search (sail, boat, skipper, club) · Hull profile (names and skippers by year, every result
linked to the official page, trend by event type, renames, new skippers) · Events (filter by
year, region, host, source) · Season/region rankings (minimum-events filter) · Class
participation over time (boats per year per region) · Data coverage (sources, years, gaps).

Show place and fleet size next to every score, mark mixed-class results, and credit each
source with a link on every event.

Build-time rules: drop events in `data/identity/excluded_events.csv` (outside North America);
a mixed event counts toward season scores only with at least 3 J/105s (list smaller ones,
with "J/105s: n of division_size", but leave them out of averages); fill missing states from
`host_clubs.csv` (`regions.event_state`).
