---
name: identity
description: Resolve sail numbers to hulls, review the alias, nickname and shared-boat tables, and detect renames and new skippers of record. Flags ambiguous cases for a human instead of merging silently.
---

# Hull and person identity

Tables in `data/identity/` are reviewed by a human; every row needs a reason.

| File | Columns | Use |
|---|---|---|
| `aliases.csv` | sail, hull, boat, reason | typo / renumber / PHRF number → hull |
| `nicknames.csv` | printed, name, reason | e.g. "Buckey" → Lenny Rezabek |
| `shared_boats.csv` | boat, note | club boats; skipper changes aren't ownership changes |
| `hull_notes.csv` | hull, note, source | facts confirmed by the user (moves, sales); shown on hull pages |
| `split_numbers.csv` | sail, boat, hull, reason | one number carried by two hulls; `boat` prefix picks the hull |
| `unnumbered.csv` | event, boat, hull, reason | results printed without a sail, matched by boat name |
| `optout.csv` | printed, action (remove/replace), replacement, requested, note | see `privacy` |

Code: `src/j105/identity.py` (`sail_key`, `hull`, `person`).

## Finding candidates

Across all `data/raw/*_events.json`, group results by `sail_key(sail)` and look for:

1. **Same number, different boats**: several boat names in one year, or in different regions
   the same year (Kinetic #401 SF vs Kinetic #440 Seattle are different hulls).
2. **Same boat, different numbers**: one boat name + skipper under two keys (likely a typo,
   renumber or PHRF number such as 51911 or 33406). Numbers above ~700 are probably not hull
   numbers.
3. **Yacht Scoring `ys_boat`**: the same `boatId` under two sail numbers is strong evidence of
   one hull; one `boatId` with two numbers in one event is a scorer error.
4. **Renames**: the year's most common name differs from the previous year's.
5. **New skipper of record**: the year's most frequent skipper differs and is still skipper of
   record the next season. Ownership is inferred, never asserted; say "skipper of record".
6. Placeholder sails (`TBD`, `NA`, empty) and charter boats at championships: never merge them.

## Acting

- Only add an alias when evidence is clear (name **and** skipper continuity, or YS `boatId`).
  Write the reason. Run `uv run pytest` (a test requires reasons).
- Anything ambiguous: list it for the user with the evidence (events, years, URLs) and leave the
  records separate.
- Co-skipper cells ("A / B", "A & B") credit every named skipper (user, 2026-10-19).
- Confirmed by the user: Creative is hull 422 (it also races as PHRF 51911). Hull 32 sailed in
  SF (Jitterbug, Melilani) and was sold into the Seattle fleet (Counterpoint). Record new
  confirmations in `hull_notes.csv`.
- A YS `boatId` follows the owner's profile, not the hull: charter teams at championships keep
  their `boatId` on a borrowed hull. Supporting evidence only.
