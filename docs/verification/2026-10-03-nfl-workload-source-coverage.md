# NFL workload history coverage in the October 3 prequote cohort

This is a coverage audit, not a prediction backtest. The input is the independently verified October 3 private research pair. The script replays its exact market cohort, model forecasts, crosswalk and six hash-pinned nflverse files as they stood before the quote decision. It then checks whether each unique receiving player/prop forecast has 20–40 prior played games with a recorded stat row and target count for every game. The recent five must average at least two targets, matching the frozen workload candidate's floor.

| Stage | Unique player/prop pairs |
| --- | ---: |
| Quoted receiving contracts | 336 contracts |
| Source-backed role forecasts | 233 |
| Complete recorded target history and workload floor | 137 |
| Positive offensive snaps but at least one missing player stat row | 85 |
| Complete rows but low recent target workload | 11 |

Thus the new target-based transfer is feasible for **137/233 (58.8%)** of this source-backed role-forecast universe, or **137/336 (40.8%)** of observed receiving contracts. These are upper-bound source-data checks, not actual sportsbook shadow predictions: sportsbook players, exact quote identities, database row joins, timing, roster and market-pair gates can further reduce coverage. Jacksonville aliases also remain under the historical v3 receipt in this cohort. Do not interpret the 137 as qualified picks or as successful outcomes.

The missing-row cases are not automatically zero targets. The [nflfastR player-stat aggregation code](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R) builds weekly player records from play statistics, while [nflverse snap counts](https://github.com/nflverse/nflreadr/blob/main/R/load_snap_counts.R) are a separate source. It is an inference that some snap-positive players with no weekly stat row had zero receiving opportunity; these sources alone do not prove that for each game. The forward workload candidate correctly abstains on such rows. A future recovery needs an independently replayable play-level or explicit game-level source, a new model/policy version, and a fresh prospective cutoff. Lowering history or qualification gates would not prove an edge.

Reproduce with no network or paid request, using the restored private prequote pair directory:

```text
python docs/verification/2026-10-03-nfl-workload-source-coverage.py \
  --root PRIVATE_VERIFIED_PAIR_DIRECTORY \
  --output .local/nfl-workload-source-coverage-20261003.json
```

The ignored aggregate result SHA-256 is 8c5a074e075afdb8694ccb432768748ceb075b1958012b01b070e51288570ee8. No player-level results or source assets are committed. The October 3 pair and all original frozen v3 receipts remain unchanged. There are still no prospective outcomes for this candidate, matched-price skill proof, or validated 75% win rate.
