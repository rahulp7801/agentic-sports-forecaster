# NBA, NFL and CFB source chronology checkpoint — 2026-10-02 UTC

## What the stored data can establish

Read-only aggregate query of `nba_player_gamelogs` on 2026-10-02:

| NBA season | Rows | Game dates | Stored `source_observed_at` |
| --- | ---: | --- | --- |
| 2025 | 26,651 | 2025-10-21 to 2026-04-12 | 2026-09-23 18:51:38 UTC |
| 2024 | 26,306 | 2024-10-22 to 2025-04-13 | 2026-09-23 18:53:09 UTC |

All 52,957 current rows have a nonnull observation timestamp after their game date. This does **not** establish their first arrival: the official NBA upsert previously replaced `source_observed_at` on every repeat pull. These records cannot now prove what the model knew before the historical games. A retrospective win rate or edge computed from them would not be a valid pregame claim.

## Repair

The official NBA and CFB game-log refreshes now retain the **entire earlier source receipt** when the normalized row, source provider, and row commitment are unchanged. That includes `source_observed_at` and the batch, player-asset, and schedule-asset hashes. A changed field, including NBA workload fields outside its settlement hash, advances the observation time and all source hashes together. An unrelated change elsewhere in a refreshed source asset cannot pair a later batch hash with an earlier row-observation time.

CFB's official refresh had the same overwrite path. A read-only check of the October 2 Virginia Tech–Pittsburgh athlete cohort found stored primary-row observations ranging from September 19 through October 2; some October 2 rows arrived **after** the prior quote capture. Their current timestamps cannot reconstruct the earlier as-of cohort. Prospectively captured, immutable source rows remain necessary for that comparison.

The NFL weekly player-stat and offensive-snap refreshes also used the unconditional upsert. A frozen Linux 3.12 audit of one read-only hosted paper-selection snapshot verified all seven NFL raw-model receipts; two original estimates exceeded 75%, but neither had complete current-role evidence. For the receiving offer, the original model recorded 36 history games while only 34 primary player-stat rows now have `source_observed_at` at or before its history cutoff. The two excluded rows are 2026 weeks 1 and 2. The current database has all 36 rows and 34 positive-snap games at that cutoff. The old observation timestamps were mutable under the existing refresh, so these facts do not establish when either row first arrived and cannot repair the immutable paper receipt.

Both NFL refresh paths now use the same first-receipt preserving upsert as NBA and CFB. An unchanged normalized stat or snap row retains its original observation time and batch commitment even when another player changes the source batch. A changed row advances its source receipt. Future as-of role capture can now use stable first-arrival evidence; earlier overwritten timestamps and missing paper context remain unavailable. The original NFL probability, role candidate formula, settlement verifier, pick gates, paid collection and frozen evaluator versions are unchanged.

`NBAQueryBuilder` supports an explicit, timezone-aware `observed_before` parameter and applies it **before** the recent-game limit, including the broad-history fallback. It excludes rows with unknown observation time. This parameter is opt-in: the frozen `empirical-jeffreys-v4` production NBA forecast path and its qualification thresholds are unchanged. Activating this as a production input requires a separately frozen model/evaluation version and forward, matched-price evidence. Existing frozen paper protocols pin the shared model contract and ledger bytes; those files were not changed.

## Verification and next evidence

- Full offline suite: 1,791 passed, 68 skipped on this branch.
- Focused SQL fixture verifies a late-arriving prior-game row is excluded before the recent-game limit; naive cutoff timestamps fail closed.
- Disposable PostgreSQL tests verify unchanged NBA/CFB refreshes preserve the complete earlier receipt and genuine corrections advance the stat, observation time, and source hashes together. These tests are skipped locally without `SPORTSBET_TEST_DATABASE_URL` and run in the repository's PostgreSQL CI job.
- A disposable PostgreSQL test runs both real NFL ingestion functions with an unrelated batch change and then an actual player/snap correction. It checks preservation of both original source receipts followed by advanced timestamps and hashes on correction.
- Next NBA season's quote captures must archive exact source-aware inputs with immutable receipts before measuring a new version against same-book matched prices and authenticated results. The existing September archive alone cannot certify a 75% win rate or positive edge.
