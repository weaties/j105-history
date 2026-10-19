---
name: verify
description: Compare rebuilt standings with each event's official places and totals; run the automated consistency checks and spot-check events by hand. Reports mismatches, never silently fixes data.
---

# Verify standings

1. `uv run j105 verify`. For every scored event with more than one boat it checks that:
   - `fleet` equals the number of results;
   - places run 1..n (an unbroken tie may repeat a place only when net points are equal);
   - net points never fall as place rises (low-point scoring);
   - no sail number repeats within an event;
   - there is an official `url`.
   It then prints five random events per source to check by hand.
2. Spot-check those events on the official page: fleet size, the top three places, and net
   totals. Also check a mixed (`mixed: true`) event and an event with ties.
3. For each problem decide: parser bug (fix the code and add a test), scorer data quirk (leave
   the data, note it), or identity issue (see `identity`).
4. **Never edit results to match.** If a correction is needed, record it with a reason (in a
   reviewed table, as with aliases) so the build applies it reproducibly.
5. Report: counts checked, problems by kind, what was fixed, and what is left for the user.

## Known, accepted quirks

- Clubspot hides tiebreaks: boats tied on net may be in the wrong order.
- Repeated sail numbers in an event are usually scorer data (charters entered as `TBD`, typos,
  or the same boat entered twice as in Yacht Scoring event 50582).
- Regatta Network prints unbroken ties (three boats 10th on 39 points).
