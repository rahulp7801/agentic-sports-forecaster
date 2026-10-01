# Individual pick accuracy research v1

This fixed offline experiment tests whether current form can filter overconfident individual selections. It does not combine legs or promise a win rate. Generated results and player details stay private.

## Fixed rules

Reconstruct current-history core probabilities using the existing as-of source and supplement rules. Start with the original earliest EV-qualified selection per player/game using matching recorded prices. Rejecting one never admits a later quote or another market for that player/game.

Report three nested cohorts: original model probability at least75%; additionally last10 observed games with Jeffreys estimate at least75% and newest game at most30days old; additionally at least2 current-season/current-team games and current-role prior20 estimate at least75%. These constants are fixed before this experiment runs. The current-role prior is the older-game Jeffreys estimate, not the full sample reused as independent evidence. Archived roster observations must precede the forecast, be at most1hour old, and retain source commitments. Source row digests bind each historical value. All missing/ambiguous context abstains.

Current-role calculations are stat-only counterfactual diagnostics and do not replace the frozen complete-participation shadow. Archived roster summaries cannot reconstitute raw roster feeds. Typed, dated teammate reports support descriptive slices only; legacy or unknown relationships stay unknown. No causal teammate adjustment is fitted.

## Evidence

Report original and retained counts, settled wins, pending selections, unique games, actual-price ROI, game-cluster intervals, rejected-cohort performance and per-pick reasons. Consensus is a filtering score, not a calibrated probability. The archive was already inspected; all results and intervals are exploratory, including any slice above75%. Multiple rules and repeated players require fresh prospective confirmation before any product claim. No production qualification, model versions, forward protocols, quotas or collection changes are included. NBA cannot be evaluated without retained priced observations.

Run privately with `python -m sportsbet.quant.individual_pick_accuracy --ledger-path PRIVATE_LEDGER --history-path PRIVATE_HISTORY --output PRIVATE_REPORT`.

## Missing temporal history

When refreshed current-season rows no longer retain their earlier versions, the as-of replay can lose current context. Report this as not evaluable, not as evidence that the current-context rule fails or that the original production forecast used old history. Separately inspect original workload and role receipts using their unchanged frozen verifiers; never use a receipt from a later quote to fill an earlier selection. Report verified feature availability and recent-game age without fitting another policy.
