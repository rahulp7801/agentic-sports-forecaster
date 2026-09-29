# NFL recent-role prospective experiment v2

## Frozen contract

- Candidate: `nfl-recent-role-shadow-v2`.
- Policy: `complete-receiving-current-role-prior20-v2`.
- Baseline: `empirical-jeffreys-v4-nfl-history-v1` and `nfl-explicit-receiving-v1`.
- Prospective start: `2026-09-29T06:15:00+00:00`.
- Markets: receiving yards and receptions, nonnegative half-lines only.
- Scope: all unambiguous GSIS/PFR/ESPN bindings in the already pinned identity artifact; exact current-roster confirmation is required for every capture.

The original v1 source, implementation, records and evaluator remain unchanged. There are no fitted coefficients or retrospective performance-based scope choices.

## Input eligibility

Use 20?40 most recent pregame records from the prior two seasons and current season. Every modeled game must have verified positive offensive participation, and every observed offensive game in the retained season window must have primary or independently verified explicit receiving statistics. Missing games and missing categories remain unknown. Source observations and archived supplement insertions must precede the production history cutoff. Receipt capture must precede inference; the exact cutoff, sample count, empirical probability and mean must reproduce the corrected baseline.

Primary arrivals cannot duplicate supplements; conflicts cause abstention. Current-team/current-season games require the exact provider roster identity, fresh observation and source commitment. At least one current-role game is required. Negative observed receiving yards remain valid; receptions cannot be negative.

## Candidate formula

For a selected threshold, form a Jeffreys-smoothed prior from older games: `(older_hits + 0.5) / (older_games + 1)`. Combine current-season/current-team hits with 20 prior pseudo-observations: `(current_hits + 20 * prior) / (current_games + 20)`. Under probabilities are exact complements for these half-lines.

This isolates the value of current role against the corrected full-history baseline. It does not assert a causal teammate effect or apply a probability adjustment to consumer picks. Current participation summaries remain descriptive evidence.

## Receipts and resource bounds

Read once per event under a read-only repeatable-read transaction, with a five-second scanner budget, at most 64 athletes and 80 rows per player/source. Retain only whitelisted stat and source fields. Input receipts use deterministic gzip/base64, a SHA-256 of canonical uncompressed JSON, and explicit byte counts. Compressed input is capped at 48,000 bytes; decompression is capped at 200,000 bytes and rejects trailing members. No new provider requests are introduced.

The ledger independently recomputes the candidate and owns the recording timestamp. Late or invalid candidate receipts cannot change primary probabilities, accepted picks, stake or immutable retry identity. They become unavailable with a bounded reason.

## Evaluation and activation boundary

Select the earliest attempt per event/player/market/threshold before availability, price-pair or outcome filtering. Retain unavailable attempts in the denominator. Use authenticated settlements and matching recorded market prices. Require at least 50 independent paired games and negative upper 95% confidence bounds for candidate-minus-production and candidate-minus-market Brier and log loss under both game and player clustering. Promotion is always false in the experiment report. No candidate acceptance policy or ROI is inferred.

A future production change requires separate evidence review and a new model version. Qualification thresholds, paid collection, credit limits and pregame reserve are unchanged.
