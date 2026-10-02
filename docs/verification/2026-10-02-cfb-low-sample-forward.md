# CFB low-sample forward research

## Measured gap

The read-only October 2, 2026 Virginia Tech at Pittsburgh forecast cohort has 46 recorded offers from 12 distinct athletes. Forty-one offers have fewer than 20 prior games and were marked `insufficient_sample`. The other five have 20–29 games; three had no positive model edge and two failed the confidence floor. No offer qualified. This is a coverage fact, not evidence that a lower sample floor would be profitable.

The existing `cfb-team-role-shadow-v1` requires 20–40 games to reproduce its baseline, so it cannot evaluate the forty-one low-sample offers. This new, separately versioned candidate covers 4–19 source-verifiable prior games. It shares the existing bounded, exact-athlete, as-of loader; it adds no odds requests or provider cost.

A separate read-only source check at 2026-10-02T06:40Z found that 31 of those 41 recorded offers had 4–19 presently available source rows and at least two recent rows with the roster team. This is an **upper bound on possible coverage at a future fresh quote**, not a retrospective candidate count: some rows arrived after the old captures, and the exact source and baseline checks still have to pass at capture time.

## Fixed hypothesis, before new results

For a half-integer line, compute the production Jeffreys pooled over frequency from all available prior games. Take at most the last five consecutive games with the athlete's current roster-confirmed team and compute their Jeffreys over frequency. The candidate is their weighted average with eight pseudo-games on the pooled estimate. Fewer than two current-team games, fewer than four total games, an identity/source/timing conflict, or a production-baseline mismatch makes the candidate unavailable. The constants `recent_games=5` and `prior_strength=8` are fixed exploratory choices, not fitted or validated edge parameters. Its first eligible capture is 2026-10-02T08:00:00Z.

The worker stores the candidate and compressed normalized source rows inside the immutable private prediction payload, bound to the exact quote and roster. A separate read-only audit chooses the earliest offer before outcome filtering, verifies the database-owned receipt and recomputes the candidate, then waits for a matching same-book price and authenticated result. It compares game- and player-clustered Brier and log loss against both the original model and de-vig market. Fewer than fifty paired decided independent games per market cannot support predictive evidence. Even a supportive scorecard has `promote=false`: a new, predeclared recommendation/ROI policy is required before changing consumer picks.

Public model probabilities, the 20-game qualification floor, other thresholds, stake behavior, and the staged paid-credit reserve remain unchanged. Keep detailed research reports and source rows private; do not publish a win-rate or edge claim from a small or historically backfilled cohort.
