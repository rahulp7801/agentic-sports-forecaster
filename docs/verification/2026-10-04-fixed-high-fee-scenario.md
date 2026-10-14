# Pregame fee scenario for the original eleven high-probability NFL decisions

The original October 4 stat-only paper cohort fixed 70 decisions before any
selected kickoff. Its separately declared model-probability-at-least-75%
diagnostic contains exactly **11 NO decisions over eight games**, ticker-set
SHA-256 `b3383ce6c65abac15e17b69a8063393c75218e07ce38d6c1cd898fcac8c8c42e`.
This outcome-blind report keeps those exact eleven and does not alter the
model, ask prices, five-point paper policy, or consumer qualification.

After the naturally scheduled 17:00, 20:05 and 20:25 kickoff-group fee and
exact-ask receipts existed, the separate
`kalshi_stat_only_high_fee_scenario` tool replayed every original pinned
model/market/source input, the fixed high-probability ticker digest, the
strict last-20 control, and all relevant raw public fee/quote receipts. It
made **no new venue request**, sportsbook request, order, or outcome lookup.
All eleven exact later asks had a modeled one-contract cost. The ignored
report is `.local/stat-only-high-fee-scenario-20261004.json` in the durable
private checkout, SHA-256
`ef0f936e85fd52a82ac64dd5ae8ad65624209dea8329ea3c894164c2881aa9ff`,
and has a byte-identical backup under the outer workspace's ignored
`.local/stat-only-high-fee-scenario-20261004-backup/`.

| Hypothetical eleven one-contract buys | Direct fee mode | Nondirect fee mode |
|---|---:|---:|
| Later displayed asks plus modeled taker fees | $5.9399 | $5.97 |
| Binary wins needed to exceed cost | 6 | 6 |
| Sum of frozen model win probabilities | 8.8150 | 8.8150 |
| Sum of strict last-20 win probabilities | 8.0238 | 8.0238 |
| Model-implied units after modeled cost | +2.8751 | +2.8450 |
| Strict-prior-implied units after modeled cost | +2.0839 | +2.0538 |

These positive modeled expectations are **not** realized return or evidence of
an executable edge: the model was overconfident in the separate unpriced 2026
stress test, the asks were displayed but unfilled, and the eleven outcomes are
unknown and correlated across eight games. Six wins would exceed the
hypothetical one-contract cost but would be only 54.5% of the selected
contracts; an observed rate of at least 75% among eleven requires **nine**
wins. Neither threshold is a guarantee of future performance. Exact venue
results must authenticate at or after the full October 6 06:15 UTC gate;
the primary 70-decision denominator and later independent-game test remain
unchanged. `edge_established`, ROI, CLV and consumer qualification stay false.

The tool requires the original ignored cohort directory as `--receipt-dir`
and the original pinned pair, market, forecast, quotes, decisions, sources,
schedule and strict-control paths. Run its CLI only with those files and a new
exclusive ignored output. Focused missing/cross-group/full-cost tests passed;
the real receipt replay completed before kickoff.
