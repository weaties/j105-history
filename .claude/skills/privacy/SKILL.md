---
name: privacy
description: What personal data may be stored and published in the J/105 results database, and how to handle a request to remove or correct a person's name.
---

# Privacy and redistribution

## Store only

Boat name, sail number, skipper/owner name as printed, home club, home city/state when the
scorer shows it, build year — what public results already publish and the analysis needs.

## Never store

US Sailing or World Sailing membership numbers or classifications, email addresses, phone
numbers, crew lists (Yacht Scoring `/boats` returns `crewNames` and membership data: drop them
in the collector). If any of these appear in a committed file, remove them and tell the user.

## Removal or correction requests

1. Add a row to `data/identity/optout.csv`:
   `printed,action,replacement,requested,note` — `action` is `remove` (shown as
   "(name withheld)") or `replace` (use `replacement`). `printed` is the name as it appears
   after tidying; add one row per spelling.
2. Never edit `data/raw/*_events.json`; the build applies `optout.csv`.
3. Rebuild and republish (see `publish`), then confirm to the requester. Aim for days, not weeks.
4. Commit with a message that does not repeat more personal detail than the table holds.

## Redistribution

- Check each source's terms before redistributing raw data. Raw caches (`data/raw/cache/`) are
  git-ignored and not shared.
- Publish derived standings with attribution and a link to the official results on every
  event.
