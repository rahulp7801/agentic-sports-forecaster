# Tracking sample coverage — 2026-09-29

## Change

New NFL tracking evidence retains the season, week and team of every row in its existing pregame sample, plus the captured roster team. The API validates the exact sample count, unique periods, allowed season/week range and roster-team binding. Invalid coverage is omitted without altering the underlying forecast probability.

The forecast evidence panel distinguishes current-season weeks and weeks with the captured roster team. It names represented teams, unknown teams and gaps before the target week. Gaps may reflect byes or missing records. Historical forecasts without these retained fields disclose that limitation; current data must not be used to reconstruct their past context.

## Boundaries

- Same maximum eight source rows and observation cutoff, applied before the window.
- Same tracking metrics, model versions, probabilities and qualification thresholds.
- Tracking remains descriptive and does not establish validated incremental edge.
- No stored forecast rewrites, quote collection, subscriptions or purchases.
- Paid quota limits and staged reserve unchanged; PR #194 remains excluded.

## Verification

Focused tests cover cross-season/team samples, aliases, unknown teams, duplicate/future/invalid periods, roster mismatch, legacy records, repeat public projection and unchanged probabilities. PostgreSQL coverage checks sample identities against the source-observation cutoff and latest-eight window. A read-only production loader probe checks that the real database returns the same structured coverage; private artifacts remain local.

## Next evidence checkpoint

At the next naturally scheduled pregame scan, verify retained sample periods in a new forecast and the public API. Do not collect replacement quotes or rewrite older forecasts to manufacture this check. Continue the existing frozen prospective evaluations only after matching games and authenticated settlements become available.
