# Independent prospective NFL pair series

`kalshi_pair_series_eval.py` combines **already frozen** NFL model/market
pairs with separately retained exact-ticker venue settlement archives. It
makes no network call. Each pair is independently replayed against its
hash-pinned prequote source files before a result contributes to the series.

The series rejects repeated Kalshi milestone IDs and repeated game fixtures
(start time and two team target IDs) across cohorts. It also rejects mixed
shadow model versions and stale quote/model pairs. This prevents adjacent
captures of the same Sunday games from inflating the independent-game count
or silently combining a changed model with an earlier version. A future v4
series starts at zero verified games even though the October 3 v3 cohort
already contains 15 distinct games. Missing, invalid, or unavailable venue
results stay in the forecast denominator and make the series incomplete.

The aggregate reports model-minus-market and model-minus-prior-20 Brier and
log-loss differences, weighting games equally, then players within game,
then prop contracts. It uses the frozen paired evaluator's deterministic
game and player cluster intervals. The **forecast skill gate** requires all
forecast results authenticated, at least 50 distinct verified games, and
upper 95% cluster bounds below zero for both metrics and both comparators.
Even a passed skill gate would not prove an executable betting edge:
displayed midpoints are not filled prices, and fee, slippage, participation,
and closing-line evidence remain separate. The report always leaves
`edge_established=false`, `qualified_picks=0`, and ROI/CLV null.

After settlement evidence exists, create an ignored private manifest such as:

```json
{
  "protocol": "kalshi-nfl-independent-pair-series-v1",
  "cases": [
    {
      "pair": "pair-1.json",
      "market_archive": "market-1.json",
      "source_dir": "sources-1",
      "settlements": "settlement-1.json"
    }
  ]
}
```

Run:

```sh
python -m sportsbet.quant.kalshi_pair_series_eval --manifest .local/series-manifest.json --output .local/series-report.json
```
 The source
directory for each case must contain the six **exact** asset bytes pinned in
that pair's manifest. The settlement archive must be an authenticated
postgame exact-ticker read; the series does not fetch it or invent missing
outcomes. October 3 outcomes are unavailable before 2026-10-06 06:15 UTC.
