# Model uplift over strict recent history in the fixed NFL paper cohort

The October 4 stat-only paper cohort selected 70 original decisions in 15 games.
Its model uses recent role features and a broader history baseline. A separate
pregame receipt fixed the strict last-20 played-game probability at the same
line for every forecast. The model gave some selected sides materially more
win probability than that simple current-form control. This diagnostic asks
whether that added probability was justified by later authenticated outcomes.

The groups use the **original selected side** and no outcome: model chosen-side
probability minus strict last-20 chosen-side probability is at least 0.05,
versus the remaining decisions. The fixed paper receipt, independent prior-20
receipt, exact source replay, and immutable subgroup ticker commitments give:

| Group | Fixed decisions | Games | Sorted ticker-set SHA-256 |
| --- | ---: | ---: | --- |
| Model uplift at least 5 points | 23 | 13 | `406c4d3bdd3121d3f8778a92a0cd03faa5328fec703b5eff8fe3802e0dc2f966` |
| Other original decisions | 47 | 15 | `d4db3e9b7c7dba1f549922636b83ef2d4f328e93ebbad7a88d75c30c4d218c57` |

The threshold matches the paper policy's five-point scale but **did not
select** the original decisions. This grouping was specified after some
selected October 4 games had started. The authoring check read no settlement
or outcome, but the timing and inspected earlier research mean this is an
exploratory diagnostic, not an untouched prospective test. The overlapping
13 and 15 game counts cannot be added to make 28 independent games.

The separate `kalshi_stat_only_recent_gap` scorer replays the original pinned
452-contract market/source/forecast/quote/decision receipts and the fixed
strict last-20 receipt. It refuses changed group membership, ticker digests,
or the wrong chosen-side model value. Before reading a result file, it requires
the full October 6 06:15 UTC result gate. It then checks the complete venue
capture wrapper, clock proof and exact contract results. Every original
decision stays in its group denominator. Missing results yield only a clearly
labeled verified subset; full win rates remain null until the group completes.
For authenticated results with the same exact two-sided price, it reports
model, strict recent-history, and market Brier/log loss, plus existing equal
game and whole-game/player uncertainty intervals. Neither a favorable subgroup
nor the full 15-game cohort can satisfy the existing independent 50-game
probability gate or establish after-fee executable returns.
Intervals remain null until at least two distinct verified games and players
have paired prices, avoiding a degenerate single-game interval.

The outcome-blind replay of the actual local receipts reproduced 452 original
contracts, 70 decisions, both fixed ticker hashes and group sizes. It opened
no settlement file and made no market, sportsbook or paid-provider request.
The focused new and adjacent scorer tests passed 10/10. A real pinned-input CLI
rehearsal with a deliberately nonexistent settlement path exited at the time
gate and wrote no output; it did not open a result. Run the diagnostic only
after the original authenticated settlement receipt exists:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_recent_gap `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --control .local/kalshi-stat-only-fixed-prior20-control-20261004.json `
  --settlements .local/stat-only-settlement-20261006.json `
  --output .local/stat-only-recent-gap-after-result.json
```

The original model, paper selections, strict control, evaluation versions,
consumer thresholds and qualification remain unchanged. This diagnostic has
`probability_support=false`, `edge_established=false` and no filled return.
