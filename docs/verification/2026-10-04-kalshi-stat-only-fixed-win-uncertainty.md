# Pregame-fixed NFL paper win-rate uncertainty

The original October 4 stat-only paper policy selected **70 contracts in 15
games**. The separate, already declared model-probability >=75% diagnostic
contains **11 of those contracts in eight games**. These denominators are
fixed before any selected kickoff. Several contracts share a game, so a raw
contract win fraction alone can make a lucky slate look more repeatable than
it is. Neither group has a verified outcome yet.

`kalshi_stat_only_win_uncertainty` is a separate postresult descriptive audit;
it leaves the frozen primary evaluator, model, 70 decisions, 11-decision
threshold, quotes and prices unchanged. It replays the pinned model/market/
source/decision preflight, refuses any settlement read before **2026-10-06
06:15 UTC**, checks the full 452-contract capture wrapper and exact venue
results, then scores only the two original fixed groups. Missing or nonbinary
results remain in the original denominators. Verified-subset fractions are
labeled as incomplete; full rates and whole-game bootstrap intervals remain
null until every selected outcome in that group authenticates.

For a complete group, it reports the contract-weighted and equal-game win
rates plus deterministic 10,000-draw whole-game percentile intervals, with
seed 20261004. Resampling keeps all contracts from a game together. These are
descriptive small-slate intervals, not a proof of 75% future performance.
There is no fee/fill/slippage/CLV evidence or executable edge in this report;
the separate frozen fee and paper-result scorers retain those boundaries.
No new provider request, paid credit, order, wager or result has been made.

Run **only after** the actual full venue receipt exists, to a new ignored
output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_win_uncertainty `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --settlements .local/stat-only-settlement-20261006.json `
  --output .local/stat-only-fixed-win-uncertainty-after-result.json
```

A real pinned-input dry run with a nonexistent settlement path failed before
opening it and wrote no report. Complete, missing and mutated synthetic
outcome tests and the adjacent frozen-paper tests passed 7/7. Full backend:
**2,082 passed, 72 skipped** (seven existing pandas warnings). This is a
pregame commitment to how later correlated results will be described, not a
new rule for choosing candidates after their results are known.
