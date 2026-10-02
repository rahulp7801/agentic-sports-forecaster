# Prospective CFB team-role shadow

This private research path records a separately versioned probability on future exact CFB offers. It does not change the production Jeffreys probability, confidence interval, recommendation policy, stake, or dashboard pick.

## Why prospective capture is necessary

The earlier CFB team-context protocol was exploratory on reused game outcomes. A read-only chronology audit on October 2 found that primary 2024 and 2025 CFB rows in the current database carry September 19, 2026 observation timestamps; current 2026 rows carried September 30 timestamps at that check. Refreshes can replace these timestamps, so they do not prove first arrival. None of the inspected historical rows had a retained pregame source receipt. A retrospective calculation using the final rows is useful for finding a failure mode, but cannot establish pregame source availability or a matching-price edge. Keep the detailed local report and raw rows out of GitHub.

## Fixed forward candidate

The version cfb-team-role-shadow-v1 uses the existing, previously specified last-observed-team candidate: the most recent contiguous team segment gets its empirical over count, shrunk with 20 pseudo-games at the older segment's Jeffreys probability. A roster team that differs from the last source-observed team produces an unavailable candidate. A single-team history leaves the production probability unchanged. The fixed strength and segment rule were not selected from the new October 2 quote cohort.

The worker captures the same 20–40 most recent non-null game rows as the existing CFB model, using exact athlete IDs, a pregame game-date cutoff, source-observed timestamps, and the existing supplement insertion cutoff. Each normalized row's record hash is checked. The roster's exact ESPN athlete ID and committed team are bound to the candidate. The candidate must reproduce the production sample, mean, and probability before it is recorded. Inputs are bounded, compressed, and sealed with the exact offer; the existing prediction-table trigger adds a server-owned pregame insertion timestamp and payload hash. An unavailable read remains unavailable and never changes a consumer forecast.

## Evidence gate

Run python -m sportsbet.quant.cfb_team_role_audit --output <private-local-report.json> against the configured read-only hosted audit source. The scorecard selects the earliest eligible offer before checking candidate status, market pairing, or outcome. It verifies the immutable prediction payload and server timestamp, then requires the sealed candidate, matching recorded sportsbook price, and independently authenticated settlement. It compares Brier and log loss with the frozen production probability and the matching no-vig market baseline, with game and player clustering. Fewer than 50 paired decided games per market remain insufficient_data; even a supportive scorecard returns promote=false. A separate predeclared recommendation and hypothetical ROI evaluation would be needed before a consumer strategy change.

Do not upload the report, source rows, or team-context details to a public repository or CI artifact. No extra Odds API request, cap or reserve change, subscription, card charge, or bet is involved.

