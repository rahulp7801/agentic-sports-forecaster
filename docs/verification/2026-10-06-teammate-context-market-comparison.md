# Frozen teammate-context results and exploratory market comparison

## New verified evidence

The original teammate-context score had not been run in the durable checkout.
Its exact pregame receipt and injury file were recovered **read-only** from the
old temporary checkout, verified against their existing raw hashes, and copied
into the durable ignored `.local/fixed-context-20261004` directory. No source
was recollected, updated, replaced or backdated.

The unchanged `kalshi_stat_only_teammate_context` scorer replayed the frozen
model/quotes/decisions, schedule, injury/stat sources, original context receipt
and authenticated exact-contract results. All **11** original probability >=75%
candidates have binary results: **8 wins / 11**. The original source snapshot
and predeclared high-probability strata remain unchanged.

| Original high-probability context | Wins / candidates | Games | Model Brier |
| --- | --- | --- | --- |
| Acute teammate >25% prior targets | 4 / 5 | 3 | 0.159145 |
| Acute teammate (10%,25%] prior targets | 0 / 1 | 1 | 0.801093 |
| Acute teammate (0%,10%] prior targets | 1 / 1 | 1 | 0.031339 |
| Questionable teammate only | 1 / 1 | 1 | 0.049863 |
| No reported skill-teammate risk | 2 / 3 | 3 | 0.273894 |

The major-absence high-probability bin averages **77.89%** model probability
and won 80%, but contains only five contracts across three games. Against its
matching market prices, Brier model-minus-market 95% game interval is
[-0.212168,+0.039634] and player interval [-0.231153,+0.092484]. Both cross zero.
The original hypothesis of overconfident NOs after major teammate absences is
not consistently supported by this tiny high-probability subset.

## Separate comparison defined after results

The new `kalshi_stat_only_context_price_audit` is explicitly **exploratory and
post-result**. It does not change the original scorer or pregame analysis plan.
It retains all seven original context bins, including empty/unavailable bins,
and both fixed scopes (all 70 original candidates and the original 11).

Every comparison replays the existing source/chronology gates, exact result
wrapper and independent HTTP clock proof, pinned strict recent-20 receipt,
and the original frozen context score. Missing/nonbinary outcomes remain in
the original denominator, and missing prices do not become paired results.
The matching-market probability uses the existing exact two-sided quote
parser for the same contract; YES and NO comparisons use the correct side.
The group paired metrics share identical binary outcomes and prices.

| Original context bin | Fixed / binary | Wins | Paired games | Model Brier | Market Brier | Strict recent-20 Brier |
| --- | --- | --- | --- | --- | --- | --- |
| Acute teammate zero prior targets | 5 / 5 | 3 | 2 | 0.217209 | 0.237905 | 0.196485 |
| Acute teammate (0%,10%] prior targets | 14 / 13 | 6 | 4 | 0.280315 | 0.260663 | 0.320469 |
| Acute teammate (10%,25%] prior targets | 3 / 3 | 1 | 2 | 0.433861 | 0.301092 | 0.401172 |
| Acute teammate >25% prior targets | 7 / 7 | 4 | 3 | 0.257708 | 0.265436 | 0.292760 |
| Questionable teammate only | 15 / 15 | 12 | 5 | 0.196266 | 0.263755 | 0.189229 |
| No reported skill-teammate risk | 26 / 26 | 13 | 7 | 0.275112 | 0.236492 | 0.267792 |
| Coverage unavailable | 0 / 0 | 0 | 0 | null | null | null |

Brier values are descriptive, contract-weighted **paired** errors. Smaller is
better. The six populated bins retain **70 candidates, 69 binary results and
39 wins**. One nonbinary result remains in the (0%,10%] bin, whose full-group
win rate is null. Counts across bins/scopes are correlated, not independent
replications; five games in one bin do not add five new games to another.

## Context hypothesis narrowed

The Questionable-only group won **12/15 (80%)** across five games. Its mean
paired model probability is 66.95%, market 52.30%, strict recent-20 63.97%.
The model's paired Brier/log-loss are 0.196266/0.583816 versus market
0.263755/0.721922 and recent-20 0.189229/0.564680.

The **unadjusted descriptive** market comparison game/player 95% intervals
are negative for both losses. For Brier they are [-0.201881,-0.024305]
and [-0.175671,-0.003893]; for log-loss [-0.422766,-0.045624]
and [-0.367128,-0.002842]. These are not corrected for inspecting multiple
bins, scopes, metrics and comparators after results. The recent-20 comparison
intervals cross zero for both metrics and both clusters. Its contract-weighted
aggregate error is lower than the model's; the equal-game differences are
near zero. Added predictive value from teammate context is **not established**.

The full >25%-absence group is only 4/7, despite its 4/5 high-probability subset;
the no-reported-risk group is 13/26 versus mean model probability 64.73%.
Those differences help locate calibration risks, but cannot justify learning
an injury multiplier, choosing a winning bin, changing a threshold, claiming
causality or advertising an 80% service.

The retained injury archive has asset-level publication timing and **no
individual update times**. The [general injury dictionary](https://nflreadr.nflverse.com/articles/dictionary_injuries.html)
includes date_modified, which cannot be assumed present in these retained bytes.
[ACT means active roster](https://nflreadr.nflverse.com/articles/dictionary_roster_status.html),
not game-day active.
Two candidate-level Questionable status changes were already observed in the
separate pregame refresh audit. This new report deliberately retains the
original bins. A future fresh-context test needs its own pregame derivation,
source-week/roster binding, frozen receipt and independent sample; it cannot
retrofit this result or change the existing recent-gap primary test.

The existing independent recent-gap study remains unchanged: excludes this
motivating slate, starts October 8, requires 50 independent matched-price games
and favorable game/player intervals against both market and strict recent-20.
The exploratory context report always leaves edge=false, qualified picks=0,
prospective replication=false and ROI=null. There are no fills, orders, bets
or consumer policy changes. Private release/OAuth/CI activation remains pending.

## Durable evidence and replay

| Local evidence | SHA-256 |
| --- | --- |
| Original raw context receipt | 733dc3f4a1b4d5fc85aeb32ce5f8117d264976e33a1f51933da883735484c792 |
| Original injury asset | 0d1ff127705c932b52ad4719f330cc314cfa2ef968d2abe426c5f6bc0f03228f |
| Original frozen context score | 820ec1024efeb130156e6e4589d0d4d357874b829c7cf2e78a850e3319c39d0b |
| New exploratory comparison | 2a1b2f7f84e6e8a535c40487506c9cad847ed96032432c9ed6b4310cbf11a022 |

Original semantic pregame record remains
`0fce75d466db103ace59f5adf4034c1e5a60e2fad6795d28a57eec51c269b31a`.
The same authenticated venue evidence is
`870239aff8a70237f70619a54fd732eafd8e5bec48da85742842f90c337a6981`.
Five files (111,014 bytes) have a hash-identical second local backup under the
outer workspace's ignored `.local/fixed-context-backup-20261006`; backup
manifest SHA-256 is
`87097cf021d80687909f930647a9efdf7db9d0875dce260dcf9429bea12e81ec`.
This is a same-drive copy, not an offsite backup. Raw player/source data and
private reports stay ignored and are not committed; only aggregates and code
are included in the private release.

Run from the durable private checkout, choosing a new exclusive output:

```powershell
.venv/Scripts/python.exe ops/run_paper_task.py --module sportsbet.quant.kalshi_stat_only_context_price_audit --pair .local/fixed-cohort-20261004/verified-timely-pair-20261003/pair.json --market .local/fixed-cohort-20261004/verified-timely-pair-20261003/market-archive.json --forecast .local/fixed-cohort-20261004/kalshi-stat-only-probabilities-20261004.json --quotes .local/fixed-cohort-20261004/kalshi-stat-only-quotes-20261004.json --decisions .local/fixed-cohort-20261004/kalshi-stat-only-ask-decisions-20261004.json --source-dir .local/fixed-cohort-20261004/verified-timely-pair-20261003/sources --schedule .local/fixed-cohort-20261004/team-share-sources/games.parquet --injuries .local/fixed-context-20261004/injuries_2026.parquet --receipt .local/fixed-context-20261004/context-receipt.json --settlements .local/fixed-cohort-20261004/stat-only-settlement-20261006.json --control .local/fixed-cohort-20261004/kalshi-stat-only-fixed-prior20-control-20261004.json --output .local/fixed-context-20261004/context-price-replay-new.json
```

Both actual offline runs completed. **31 focused tests passed**: new audit,
original teammate scorer and source-safe launcher. Cases cover all/empty bins,
nonbinary/missing-price retention, correct NO-price orientation, membership
and duplicate identity tampering, nonfinite inputs, correlated single-game
interval suppression, original scorer disagreement, pre-result read refusal,
and no edge/pick promotion even with synthetic perfect results. The local
runner disabled unrelated conftest/plugins; one unused asyncio-setting warning
was emitted. Cached Bandit passed for the new audit and modified launcher.
Staged redacted Gitleaks passed (33.76 KB, no leaks). All six sources bound
by the independent recent-gap evaluator have identical normalized hashes. No frontend/broad
backend rerun is claimed for this offline-only increment.

Next exact checkpoint remains **October 8 17:25 UTC / 10:25 AM Pacific**:
verify capture/publisher exits, receiving-integrity/recent-gap/source-week/
schedule/context receipts, and private server-dated pregame anchor. The new
exploratory result neither advances that checkpoint nor changes its protocol.