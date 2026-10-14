# First exact-contract forward ask check, October 3

The frozen, outcome-blind NFL pair from 2026-10-03 13:03:52 UTC had 126
hypothetical one-contract candidates under each of two fixed policies, across
15 games. These are research candidates without roster proof, fills, or
qualified consumer status. Both policies selected 127 distinct Kalshi tickers
in their union. The first board lock was 2026-10-04 12:30 UTC.

At 2026-10-03 21:31:44 UTC, `kalshi_exact_markout` retained one later raw
observation for that exact union. It replayed the pair and source archive
before collection, requested only seven batches of at most 20 tickers from
the public, unsigned `GET /markets` endpoint, and made no Odds API, order,
database, or paid request. The read adapter may retry transient failures;
the receipt records seven requested batches, not an asserted HTTP attempt
count. The ignored private raw receipt is
`.local/kalshi-prospective-20261003/exact-markout-20261003T2131Z.json`, with
evidence SHA-256
`8e66fb6e949b3edd6684412de4bd43e72aaa152c93231cebc7038a04594b8f2a`.
It retains the exact tickers, request and receipt times, complete provider
responses, and an evidence hash covering every raw page. No repeat collection
was used.

The first offline report mistakenly rejected a valid selected NO ask because
the opposite YES side displayed only 0.81 contracts. The evaluator now
requires positive depth on each quoted side and at least one displayed
contract only on the *selected* side. The same raw receipt was replayed with
that correction; the first report is superseded. The final ignored private
`exact-markout-report-20261003T2131Z-v3.json` also adds a deterministic,
whole-game bootstrap interval from the same raw response. Regression tests
cover the selected and opposite-side depth distinction.

| Frozen policy | Candidates | Matched prelock asks | Games | Ask up | Ask down | Unchanged | Mean side-ask change | Equal-game mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current-role v3 | 126 | 125 | 15 | 18 | 31 | 76 | -$0.00224 | -$0.00257 |
| Prior-20 benchmark | 126 | 125 | 15 | 17 | 31 | 77 | -$0.00232 | -$0.00268 |

The remaining contract was `inactive` in the later provider response and
stays in each frozen denominator, so `complete_candidate_markout=false`.
For the 125 matched candidates, the descriptive equal-game 95% interval is
[-$0.00640, +$0.00059] for the current-role policy and
[-$0.00650, +$0.00042] for prior-20. Both cross zero. The bootstrap resamples
whole games and is conditional on matched asks; it does not repair the missing
contract or account for researching multiple policies. Identity, line,
player, team, event, strike,
settlement-rule hash, source timing, displayed price complement, and selected
ask size are checked on every matched contract. The receipt hash, original
source hash, frozen pair hash, exact request set, page ordering, and prelock
chronology are checked before scoring.

An ask increase would be a favorable *paper* markout for the selected side;
the observed small negative average therefore does not support a positive
short-horizon price edge. This is one snapshot roughly eight hours after
the decision, with many correlated props per game. It is not a closing line,
trade fill, return, settled win rate, confidence interval, or proof that
the model has or lacks a repeatable edge. Exact venue results and more
independent prospective games remain necessary. The frozen cohort's first
settlement collection remains no earlier than 2026-10-06 06:15 UTC.

Reproduce from the ignored private pair and market archive, without another
provider request:

```text
python -m sportsbet.quant.kalshi_exact_markout \
  --pair PRIVATE_PAIR.json \
  --original-market-archive PRIVATE_MARKET_ARCHIVE.json \
  --receipt PRIVATE_EXACT_MARKOUT.json \
  --output PRIVATE_NEW_REPORT.json
```

Focused reader, markout, and fee tests: 23 passed; the final interval change
also passed 12 markout and interval tests. The preceding full Python suite:
1,988 passed, 71 skipped. The private PR is not deployed; this check changes
no consumer probability, qualification threshold, staged reserve, or
20-credit daily and 450-credit rolling paid API limits.
