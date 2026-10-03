# NFL core history shown on forecast cards

## Failure found

NFL passing and rushing forecasts use primary `player_stats` rows. The public
history card queried `dashboard_gamelog_versions`, whose NFL rows come from
the receiving-supplement reconciliation. A conflict in receiving yards or
receptions can suppress that player's whole effective receiving history even
though the passing or rushing forecast still used valid primary rows. A
consumer could therefore see missing recent form for the stat being forecast.

## Change

Migration `0044_nfl_core_dashboard_history` adds the restricted,
source-timed `dashboard_nfl_core_gamelogs_asof` projection of primary NFL rows.
It requires the `nflverse` provider, source batch and row hash fields, a
source-observation time, a player name, and one matching schedule game. The
payload exposes passing and rushing fields; receiving fields are null so they
cannot be mistaken for reconciled receiving evidence.

Only exact-player NFL `pass_yds` or `rush_yds` card requests with a target-date
and source-observation cutoff use this projection. Receiving, NBA, and CFB
history retain their existing paths. The query binds all user values and
applies both cutoffs in SQL. Role provisioning now grants the reader access to
all optional versioned history views whether it runs before or after the
migrations, while denying direct browser access.

## Verification

- Disposable PostgreSQL 16: full migration suite, 12 passed; targeted NFL
  receiving-conflict and role-provisioning suite, 4 passed. The conflict test
  confirms the normal receiving view excludes the row while the primary
  rushing view retains it, and checks the observation cutoff and ACL.
- Frontend: 322 tests passed, TypeScript and changed-file ESLint passed,
  webpack production build passed.

This repairs the *displayed* stat history and access path. It does not alter a
forecast probability, qualification threshold, frozen evaluation version, or
the retrospective/prospective outcome data. Primary source corrections can
replace an earlier row; this limited card history cannot reproduce every
historical model input. No edge or 75% win-rate claim follows from this fix.

## Row integrity follow-up

The restricted core view now includes a server-only normalized source row and
its stored record commitment. The `/api/gamelogs` route recomputes the same
SHA-256 encoding as NFL ingestion before returning any primary passing/rushing
card history. It accepts the retained legacy NFL commitment, which still
covers passing and rushing values. A missing or mismatched row makes the whole
request unavailable; the raw source row and digest are not included in the
public response. This closes the gap where a SHA-shaped stale commitment could
accompany a changed stat value on the consumer card. The source provider and
full-season batch remain outside this row-level check.

Independent Python golden digests pass in the frontend verifier for both
current and legacy rows; changed values and missing evidence fail. The full
frontend suite passed **327/327**, TypeScript and changed-file lint passed,
and a local Webpack production build completed. A disposable PostgreSQL 16
migration round-trip test passed with the new view column and existing reader
and browser access restrictions; the test container was removed. This is
descriptive-history integrity, not a changed probability or edge result.
