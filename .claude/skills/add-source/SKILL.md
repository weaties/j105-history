---
name: add-source
description: Checklist for adding a new scoring system (STYC, j105.org archive, Jibeset, Sailwave, a fleet website) as a source of J/105 standings in the common event schema.
---

# Add a source

Work in this order and stop to ask the user at the terms-of-use step if anything is unclear.

1. **Discovery.** Find how to list events and detect a J/105 class (names vary: `J/105`, `J105`,
   `J-105`, `j 105`, `1. J/105`, `Class D J-105`; regex `(?i)j\s*[/-]?\s*105\b`). Note how
   J/105s appear in mixed divisions. Record verified API/page quirks in `CLAUDE.md`.
2. **Terms of use.** Read the site's terms/robots.txt. Note in the module docstring whether raw
   data may be redistributed. If unclear, keep raw replies in the git-ignored cache only and
   publish derived standings with attribution and a link back.
3. **Module.** Create `src/j105/sources/<name>.py` with `discover()` and `standings()`, using a
   `Fetcher("<name>")` and `pmap`. Cache every reply (`cache="..."`), refetch recent events
   (`is_recent`), write `data/raw/<name>_index.json` and `<name>_events.json`. Register it in
   `SOURCES` in `cli.py` (and `_short` / `verify.FILES` if the file prefix differs).
4. **Schema.** Fill every required `Event` field. Keep `url` = official results page. Keep the
   official place; re-rank only mixed divisions (`mixed`, `division_size`). Store only fields
   allowed by the `privacy` skill.
5. **Tests.** A parser test against a small synthetic page or reply that mimics the real one
   (don't commit third-party pages). Cover: own division, mixed division, unscored, ties.
6. **Verify.** `uv run j105 verify`; then spot-check at least five events against the official
   pages (places, fleet size, net totals). Report mismatches; don't patch data.
7. **Counts.** `uv run j105 counts <name>`; report per year and region. Update the sources table
   in `CLAUDE.md` and the coverage notes in `README.md`.
8. Commit locally; ask before any push.
