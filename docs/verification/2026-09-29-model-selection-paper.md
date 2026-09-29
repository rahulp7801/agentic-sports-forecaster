# Independent prospective model-selection paper test

## Frozen scope

This adds private timely receipts for the previously researched raw-model and fixed market-prior80 selection rules. Both reuse existing natural scan forecasts; there are no quote-provider calls, quota changes, purchases, bets or public recommendation changes. The existing cross-book protocol and implementation are unchanged. No historical result or CFB/team-context artifact is published here.

- Start: September 30, 2026 00:00 UTC. Capture, quote and model-generation times must all be on or after the start.
- NFL model: `empirical-jeffreys-v4-nfl-history-v1`; CFB: `empirical-jeffreys-v4-cfb-history-v1`; NBA: `empirical-jeffreys-v4`.
- History and recommendation policy versions are fixed in the protocol. Old NFL/CFB cohorts cannot validate the new models.
- Raw and calibrated rules have separate protocol identities in the existing private `analytics.paper_selections` table. The primary hypothesis is the raw rule; the calibrated rule is secondary. Sports remain separate.
- Each rule chooses at most one offer per player/game: highest estimated return of at least 2% at the earliest eligible response, with the existing exact-source, half-line, minimum-history and five-minute freshness requirements. The prior strength remains 80.
- The first successfully retained timely selection is kept per rule/player/game. Failed or expired recording is not backfilled; subsequent natural scans can supply a later timely first receipt. This live receipt cohort is distinct from reconstructing the earliest possible historical candidate.
- Each receipt retains the original inputs and exact opposite-side price, supporting always-Over, always-Under and half-unit-per-side controls on the same selected opportunity. Embedded opposite prices must reproduce source hashes and the market baseline.

## Fixed review cohort

For each sport/rule, the review cohort consists of the first 50 games with valid receipts that have actually started, ordered by start time then game ID. All selections in those games must settle from authenticated final statistics before review. At least 100 decided selections are required. A completed cohort with fewer selections is insufficient; later games cannot be appended to make it pass. Later/unstarted receipts remain excluded and visible in the audit counts. Controls inherit the model's chosen opportunity and isolate direction value, not the whole opportunity-selection process.

The report shows hypothetical equal-stake ROI, matched control returns, paired incremental return over Under, Brier error and paired error relative to matching market probabilities. Whole-game bootstrap intervals use 10,000 fixed-seed draws and Bonferroni tails across the six sport/rule streams (approximately 99.17% per-stream intervals). Review requires all three bounds to agree: positive model ROI, positive model-minus-Under return and negative model-minus-market Brier error. These are conjunctive gates; the adjustment is across streams for each endpoint, not a simultaneous confidence guarantee for every displayed diagnostic. This preserves the prior minimum evidence requirements and adds a matched-control check. Bootstrap assumptions and dependence across repeated players still limit inference. `promote` is always false; even a passing result requires review and cannot automatically publish picks or establish a marketing claim.

## Receipt integrity and runtime behavior

The existing server-owned clock, payload hash constraint, foreign key, immutable protocol/player/game key and row-level security remain in force. The worker has SELECT/INSERT only; dashboard/browser roles have no access. No migration is required. The new hook runs after forecast persistence, separately from cross-book recording, with a three-second database envelope and two-second statement timeout. Failures are nonfatal and log only exception type. Recording stops at quote expiry or kickoff. Original selected forecasts are never rewritten.

The new implementation pins the selector, matched controls, source/chronology validators and reused storage utilities. Receipts also retain their own implementation and protocol hashes. Auditing reproduces the exact selection and compares immutable forecast inputs against the ledger; changed evidence, deadlines, identities or code fail closed. Unknown and future-dated outcomes remain pending. After the first real receipt, changing this implementation requires a new version/cohort rather than retroactively changing the experiment.

## Private verification

`python -m sportsbet.quant.model_selection_paper --output PRIVATE_REPORT.json`

This audit reads a repeatable-read database snapshot, scoped to the two new protocols and their referenced forecast IDs. It creates only the requested private local report. Do not attach research outputs to GitHub or expose them through the consumer dashboard.

Verify natural eligible scans after September 30 00:00 UTC (CFB), 00:15 UTC (NFL), and October 1 23:00 UTC (NBA). Confirm timely server-stamped receipts and frozen version identity first, then authenticated settlements. No redundant quote collection is authorized. Daily/rolling limits remain 20/450 with the staged pregame reserve. PR194 remains unapproved.
