# Exploratory edge search and robustness protocol

This offline experiment uses the existing private source-verified archive. Outcomes have already been inspected, so no historical split or favorable strategy is an untouched confirmation set. The code and fixed rules are committed before running this comparison. Private replay reports, particularly CFB/team-context results, must not be uploaded to GitHub.

## Five fixed policies

1. Raw model expected return at least 2%.
2. Model probability shrunk toward the matching market with a fixed prior strength of 80, expected return at least 2%.
3. Existing frozen cross-book candidate, unchanged.
4. Existing cross-book selections retained only when the raw model agrees with the direction of the price discrepancy.
5. Existing cross-book selections retained only when the calibrated model also estimates at least 2% expected return.

The two filtered cross-book policies do not reselect a different offer after rejection. All five use the existing exact price/source/chronology eligibility and half-line/minimum-history scope. Raw/calibrated policies compare offers available in the same retained player/game response, choose the highest estimated return at the earliest eligible decision, and allow one selection per player/game. No outcomes enter selection. Prices must remain at most five minutes old and pregame; repeated scans cannot refresh a price's first receipt. Ambiguous same-book/side prices are rejected.

## Sensitivity checks

Report every policy, with authenticated decisions, pending counts, game clusters, paired probability errors and hypothetical equal-stake returns. Show the result after removing the most profitable game, the full leave-one-game-out range, a 5% reduction in winning payouts, and the scenario where all pending selections lose. Pending scenarios never replace actual labels. A fixed September 25 UTC game-start split is descriptive only.

Also inspect opposite-side prices from different books for the exact same line and source response. Compute their conditional two-sided price margin with decimal arithmetic and reject numerical roundoff below 1e-12. Repeat with 5% lower winning payouts. These are historical price inconsistencies; execution, limits and identical settlement rules are not established by this data. They are not guaranteed profit or live recommendations.

The game-cluster intervals do not correct for strategy search or repeated players across games. Dropping a game is a concentration diagnostic, not cross-validation. No result can promote a candidate. Existing production thresholds, frozen models, forward tests, paper receipts, budgets and schedules remain unchanged.

## Reproduce

`python -m sportsbet.quant.edge_search_stress --ledger-path PRIVATE_SNAPSHOT.sqlite3 --output PRIVATE_REPORT.json`

The existing input is opened read-only. The report includes protocol, input, implementation and frozen-selector commitments. No network collection, database writes, purchases or bets occur. Thirteen focused tests cover outcome-independent selection, price timing, orientation, duplicate/conflict handling, pending scenarios, game concentration, genuine price arithmetic and exact identity constraints.
