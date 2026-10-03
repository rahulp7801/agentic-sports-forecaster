# Free CFB final-result settlement

## Failure observed

On October 2 at 04:06 UTC, the 2026 current CFB model had 103 pending forecasts across two games. The first game, North Texas at Tulsa (ESPN event `401862786`, kickoff October 2 01:00 UTC), was still in progress. The public workflow refreshed the CFB slate but skipped CFB history and settlement; those tasks otherwise depended on the paid workflow's daily operation. GitHub scheduled paid runs had delivery gaps, so final results could remain pending even when free source data arrived.

## Change

The existing public daily workflow now calls `sportsbet.cfb_public_settlement` after the CFB schedule step. It refreshes current-season CFB game logs from the existing free source, collects bounded ESPN schedule dates including the normal seven-day catch-up window, and calls the existing exact-game, exact-athlete `settle_final_props` contract. It then republishes CFB model metrics, accepted-pick history, and the existing history shadow. A failed history refresh blocks settlement; incomplete schedules remain degraded and cannot establish a missing result. The worker publishes its own pipeline:public_cfb_settlement status. If an
officially final matched game still has no verified player stat, or its stat
provenance fails, the report is degraded with a bounded final-stat evidence
count. Pending forecasts stay pending and no result is invented. Nonfinal
scheduled games alone do not trigger this source-lag state. Its free CFB steps continue after an unrelated NBA/NFL public market failure, while failed worker configuration, schema checks, or cancellation still prevent them; the overall job retains its original failure status.

It has no Odds API key, sportsbook quote collection, model change, threshold change, recommendation creation, or bet execution. The daily public trigger already exists at 13:17 and 13:47 UTC; manual `public_daily` with `sport=cfb` can run this path. The public monitor does not refresh CFB history. No extra paid scan is needed to settle a final result.

## Verification checkpoint

Focused worker tests cover successful publication, a failed source refresh, workflow scoping, and absence of an Odds API key. Existing daily/settlement/workflow suites passed locally. After authorized release, verify the first natural public daily CFB settlement report, the exact final ESPN event and player-stat receipts, and authenticated decided counts on `/api/metrics?sport=cfb`. If the source has not published a player row, keep that forecast pending and use the separately reviewed explicit final recovery only with its full proof. A settled CFB forecast is not itself a qualified pick or evidence of a market edge.

At the October 2 05:13 UTC checkpoint, ESPN marked event 401862786 final,
but the free 2026 player-box asset was last updated before kickoff and the
hosted exact-event stat table still had no rows. This is the live source-lag
case the status now distinguishes from completed grading.
