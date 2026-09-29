# Historical accuracy compared on identical records

## Finding

The public fixed-4.5-reception research datasets contain 213 highest-conviction records for 2025 Weeks 1-2 and 122 for 2026 Week 1. The existing model gets 180/213 (84.5%) and 100/122 (82.0%) correct. Always choosing Under on those same selected records gets 181/213 (85.0%) and 94/122 (77.0%); always choosing Over gets 32/213 (15.0%) and 28/122 (23.0%). These descriptive comparisons do not establish consistent model superiority, statistical significance or an edge against priced markets. The cohorts were selected retrospectively and contain no archived bookmaker prices.

## Presentation change

The landing page now shows both constant-direction baselines alongside each model headline and explicitly states the differing results. The hero reads "Forecasts you can inspect." The backtest view shows the same comparison for the selected evidence cohort and each historical replication period. Correct/Missed row filters cannot change these comparison denominators. Missing or non-boolean outcomes cannot be counted as Under successes.

This uses already-public NFL research records. No private CFB or team-context research data is published. Historical records, model/evaluation versions, confidence rules, qualification gates, credit limits and staged reserve remain unchanged. No collection is triggered and PR #194 remains excluded.

## Verification

Six public benchmark tests pass, including recomputation of all summary counts from validated published records, empty cohorts and rejection of unverified outcomes. TypeScript and focused ESLint pass. Chromium checks at 390, 900 and 1440 pixels verify both landing comparisons, the three backtest tables, stable denominators across Correct/Missed/All results, no horizontal overflow and no JavaScript errors. Mobile landing and tablet backtest screenshots were visually inspected. Repeat these checks against the deployed release after CI passes.

## Evidence still required

Retain the frozen prospective market comparison and accepted-selection return gates. These unpriced accuracy figures cannot substitute for matched market probabilities, source-authenticated results, adequate independent game coverage or prospective return uncertainty bounds.

## Deployment verifier correction

PR #263 deployed successfully and the real production browser checks passed at all three widths, including no browser console errors. Its production workflow then failed because the final verifier still required removed promotional text. The readiness test HTML had been synthesized from the verifier's own marker array, allowing that stale requirement to pass CI.

The verifier now requires both constant-direction labels, their baseline accuracies, the comparison table label and the explicit unproven-profitability disclosure. The readiness fixture is independently specified. A new test reproduced the stale-marker failure before the correction; all 15 readiness tests pass afterward, including rejection of the legacy headline and each missing required comparison/disclosure. Existing security probes, stylesheet checks, endpoint requirements and capture-identity checks remain intact. Run the corrected verifier against production, then carry the follow-up through CI and production verification.
