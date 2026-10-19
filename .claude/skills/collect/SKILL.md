---
name: collect
description: Run or resume the results collectors (discovery and standings) for one source or all of them, politely and from cache, then report counts per year and region.
---

# Collect results

All fetching goes through `src/j105/http.py` (`Fetcher`): browser User-Agent, at most 4
requests in flight, retries with exponential backoff, and raw replies cached under
`data/raw/cache/<source>/`. Never fetch with ad hoc `curl`/`urllib` in a collector.

## Steps

1. `uv sync`.
2. Discovery (only when looking for new events; slow for Yacht Scoring and Regatta Network):
   ```bash
   uv run j105 discover clubspot         # ~10 requests
   uv run j105 discover yachtscoring     # ~7,500 /splits requests first time; cached after
   uv run j105 discover regattanetwork   # ~14,000 pages first time; checked ids cached
   ```
3. Standings: `uv run j105 collect <source|all>`. This prints counts when done.
4. `uv run j105 verify` (see the `verify` skill), then report counts per year and per region,
   network requests made and any failed URLs.
5. Commit the changed `data/raw/*_index.json` and `*_events.json` with a message giving the
   counts. Never commit `data/raw/cache/`.

## Resuming and refreshing

- Interrupted runs resume: cached replies are reused, failed fetches are never cached.
- Events that ended recently (≈3–5 weeks) are refetched automatically, since results change.
- Regatta Network records every checked id in `cache/regattanetwork/checked.json`; misses from
  the current and previous year are rechecked.
- To force a full refetch of one event, delete its files under `data/raw/cache/<source>/`.

## Known gaps

- Yacht Scoring: ~96 indexed events have no J/105 block in `cumulative-result` (cancelled,
  unscored, or a listed class nobody entered). Classes named for PHRF etc. can contain J/105s
  (each boat has a `design` field) — not yet collected.
- Regatta Network: no city/state on the page; dates come from the year list.
