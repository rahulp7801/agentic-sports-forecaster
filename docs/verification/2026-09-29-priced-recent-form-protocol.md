# Priced recent-form research protocol

This is a separate offline exploratory challenger comparison. Production probabilities, qualification thresholds and frozen forward experiments are unchanged. Private input data and detailed results must not be committed.

Fixed candidates before this run: history40, recent10, exponential game half-lives8/16, and each combined with the existing 80-observation matching-market prior. Eligibility still requires at least20 actual as-of history observations; recent10 is a research feature window, not a reduction of the production sample floor. Shrinkage uses the weighted evidence mass. Missing category games are never inferred as zero or participation.

Every candidate uses identical retained quotes and source-time eligible history from current_history_replay. All source/insert cutoffs and original archive exclusions remain. Prices, identities, settlements, five-minute quote freshness, 2% expected-return research selection and first player/game exposure use the unchanged frozen research helpers. No production approval gates are claimed to have been reproduced.

Report all candidates, exact-price hypothetical returns, calibration on the earliest retained units, accuracy by predeclared probability bands, and the subset of original first selections assigned at least75%. A predicted75% is not a measured75% hit rate. Report pending outcomes, sample size, game count, and game-cluster uncertainty. No threshold is optimized on realized winners and no later quote replaces a failed first selection.

A chronological selector compares the fixed candidates by Brier loss, equally weighting game, player within game, and market within player. It requires five prior authenticated games and50 player/game exposures. Target-game labels, future entries, and outcomes observed at/after the decision cannot train it. Insufficient training causes abstention. Ties follow the declared candidate order. Also report static-candidate calibration on the identical post-warmup units.

The entire archive was previously inspected. Chronological selection is a leakage diagnostic, not a new untouched holdout. Intervals are exploratory and unadjusted for candidate search. This run cannot establish or advertise an edge; promotion is always false. Any candidate that warrants future testing needs a separately frozen prospective protocol and must not replace the existing experiments based on these outcomes.

Validation:11 recent-form tests plus15 current-history tests pass, including temporal label exclusion, target-game exclusion, evidence mass, half-lines, pending outcomes, equal exposure weighting and stable ties.

Run locally:

```sh
python -m sportsbet.quant.priced_recent_form --ledger-path PRIVATE_LEDGER.sqlite3 --history-path PRIVATE_HISTORY.json --output PRIVATE_REPORT.json
```
