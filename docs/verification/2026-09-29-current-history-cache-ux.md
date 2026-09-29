# Current-history replay and bounded public caching

## Scope

Adds a standalone offline counterfactual replay for current NFL/CFB core history rules at each archived forecast time. It retains original quote/outcome identities and source commitments, excludes later-observed history and later-inserted supplements, and applies exclusive game dates before the last-40 window. Explicit zeros and missing statistics remain distinct. It uses the production Jeffreys probability function and existing frozen research selectors and matched-price controls. It never replaces archived forecasts or runs production admission.

The archive has already been inspected. Outputs are exploratory, with game-cluster intervals, pending outcomes, coverage exclusions, and matched-side controls. Current database rows cannot reconstruct overwritten history or past effective-view conflicts. NFL passing/rushing receive an additional conservative receipt-time filter; this limitation is explicit. Source-version sample restrictions also constrain the quote universe. NBA is not evaluated without an archived quote cohort. Detailed research inputs/results remain private and are not attached to this PR.

Run privately:

```sh
python -m sportsbet.quant.current_history_replay --ledger-path PRIVATE_LEDGER.sqlite3 --history-path PRIVATE_HISTORY.json --output PRIVATE_REPORT.json
```

The history JSON contains `nfl_base`, `nfl_receiving`, `nfl_games`, `cfb`, and `cfb_supplement_receipts` captured in one read-only repeatable-read database snapshot. Forecast and history files and implementation dependencies are SHA-256 committed in the report. Receipts are `[athlete_id, game_id, inserted_at, source_sha256]`. Provide all players and seasons needed by the ledger; the supplied snapshot is not a substitute for unavailable historical row versions.

## Product changes

- Public forecast searches use a bounded per-process cache instead of persistent cache keys derived from visitor search strings. Limits: 64 entries, 16 MiB serialized payloads, 4 MiB per entry, 18 concurrent distinct loads. Identical requests share a pending load. Returned objects are cloned. Qualified-query TTL is 15 seconds; other forecast-query TTL is 60 seconds. Oversized results are returned without caching. Failures are never cached or used as stale fallbacks.
- Projection validation still runs after a cache lookup; clients still enforce quote age and game start. Existing CDN TTLs remain. Cache limits are per process and serialized payload sizes, not a promise about exact heap use or a global distributed rate limit.
- Errors and rejected requests explicitly set browser, generic CDN, and Vercel CDN `no-store` headers.
- Refresh controls reflect automatic refresh work as well as clicks. Partial refreshes are identified, failed checks are distinguished from an empty shortlist, and returning to the tab refreshes player previews too.
- Loading copy describes checking available picks. Probability differences are labeled as model differences rather than established edge.

## Verification

- 15 targeted replay tests: source and insert timing, exclusive dates, zero/null statistics, exact CFB source receipt identity, team schedule matching, duplicate keys, last-40 ordering, and production probability arithmetic.
- Read-only compiled-production-SQL parity: 12 contexts across all four supported prop types in NFL/CFB, including empty and populated NFL histories. No quote collection or database writes.
- 233 frontend tests pass, including cache concurrency/cardinality/byte/expiry/error recovery and explicit error cache policies.
- ESLint, TypeScript, and production build pass.
- Browser and remote CI/deployment checks recorded after completion.

Frozen model versions, forward protocols, qualification thresholds, collection schedules and quota limits are unchanged. No funds, credits, or bets are involved.
