# CFB receiving-history completeness audit

## Purpose

A category-oriented box-score release is not a complete participation census. A missing receiving category must remain unknown unless another archived final source explicitly supplies the statistic and independently confirms offensive participation. Excluding such missing categories can change the recent-game population used by the empirical probability model.

## Read-only command

```text
python -m sportsbet.quant.cfb_history_completeness --bundle PATH --cutoff YYYY-MM-DD --season-min YYYY --last-n-games 40 --output LOCAL_REPORT
```

The command uses the existing archived CFB final-evidence contract and a repeatable-read, read-only hosted database snapshot. It performs no source fetching or database writes and exposes no apply option. Queries bind athlete IDs, season floor, cutoff and row bound. An oversized history fails instead of silently truncating the comparison.

The audit checks the primary provider, combined asset commitment, normalized record hash and observation chronology. It accepts PostgreSQL native date and timezone-aware timestamp values, normalizes the stored VARCHAR event ID to the ingestion hash's numeric identity, and rejects invalid commitments. Stable athlete/event/team IDs govern matching; a changed player label is recorded but cannot override identity.

Each archived player/game is classified as complete, verified gap, unavailable, outside scope, missing primary game, invalid primary provenance, or source conflict. Any contradictory non-null receiving or independently checked rushing statistic prevents supplementation of that game's hypothetical sample. No new historical game rows are invented.

For each receiving field, the report reproduces production's non-null filter before ordering and limiting the recent-game window. It compares that sample with a hypothetical sample containing only the verified missing fields and records added and displaced game IDs. Remaining unverified missing categories are enumerated so a targeted repair cannot appear to certify the whole history. Invalid primary provenance prevents a misleading clean sample for that athlete.

## Interpretation boundary

This is a targeted current-snapshot diagnostic, not a historical as-of backtest, complete coverage certificate, or evidence of predictive improvement. Receipts may have been collected after the exclusive game-date cutoff. The report keeps that limitation explicit. Local source bundles and aggregate research reports are not part of this code release.

## Requirements for a future input repair

A receiving-only recovery record must never replace a complete primary game row: doing so would erase existing passing or rushing totals. A future repair must retain the original row and source commitments, bind each supplemental field to independently validated final receipts, and fail on conflicting non-null values or changed identity. Refreshing the primary release must not erase an independently recorded supplement or silently preserve one that now conflicts.

The model query, dashboard game history, and settlement reader must agree on effective values and expose reproducible provenance. Any changed input policy needs an explicit prospective version boundary; already recorded forecasts and frozen evaluation cohorts remain immutable. Coverage must be audited beyond the targeted examples before promoting a broad collection policy. This release only adds the diagnostic.

## Verification

Regression tests cover explicit zero and nonzero values, exact-ID name changes, source conflicts, native database types, corrupted/future source commitments, missing participation, exclusive cutoffs, recent-window displacement, input immutability, query binding and truncation failure. The audit can run against retained local bundles without any quote collection.
