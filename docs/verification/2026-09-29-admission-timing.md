# Admission timing after asynchronous context and database waits

## Reproduced failure

The scanner retained a decision clock from before asynchronous participation and tracking queries. Regression cases advanced that clock across kickoff, the existing five-minute quote limit, and the one-hour availability limit. Both NFL and NBA paths approved the formerly fresh selection. Even an otherwise valid delayed selection retained the earlier capture time.

## Fix

Refresh the decision clock after context queries, then apply the existing kickoff, quote and availability timing guards. Record that updated capture time in both ledger and consumer forecasts. Pass the exact timestamps into the exposure reservation and recheck after the transaction lock and immediately before inserting exposure, because synchronous database waits can also expire evidence. A rejected reservation creates no exposure.

Legacy untimed ledger callers remain compatible. Scanner admissions always supply the timestamps. The future-clock tolerance remains 60 seconds, the quote limit 300 seconds, availability limit 3600 seconds, and kickoff is exclusive. No source refresh or retry is triggered by expiry.

## Verification

End-to-end scanner regression tests cover both NFL and NBA with expired quotes, started games, expired availability, and valid delayed decisions. SQLite reservation tests inject delays after lock acquisition and after budget queries. Disposable PostgreSQL tests execute the hosted reservation adapter with the same delay boundaries. Boundary tests preserve exact thresholds and reject naive times. Existing scanner, recent-role receipt and risk tests remain required alongside full CI.

Frozen forecasts, candidate/model/evaluation versions, probability formulas, qualification thresholds, API quotas and staged reserve remain unchanged. No stored historical records are rewritten, no paid collection is triggered, and no bets are placed. PR #194 remains excluded.

## Next checkpoint

At the next naturally scheduled scan, inspect new capture timestamps, timing gate counts, server-owned shadow receipts and candidate availability. Verify valid recent-role attempts through later authenticated settlements. Do not run an additional quote collection just to exercise this change.
