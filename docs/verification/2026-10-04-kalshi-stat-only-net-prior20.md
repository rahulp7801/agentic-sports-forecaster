# Fee-aware strict last-20 control on fixed NFL paper decisions

The original 70 paper decisions, exact contracts, model probabilities and
strict last-20 pregame control stay fixed. This separate offline diagnostic
uses the naturally scheduled, independent free public fee and exact-quote
receipts for each kickoff group. It replays the full pinned source, schedule,
forecast, original decision and receipt checks before comparing the model and
strict prior on **the same** one-contract modeled-cost subset. It does not
read outcomes or change consumer qualification.

For a YES contract, the strict-control win probability is its prior over
probability; for NO it is one minus that value. A hypothetical net margin is
`win probability - (displayed side ask + modeled taker fee)`. Both direct and
nondirect fee rounding modes are retained. The five-point screen is a
descriptive probability gap, not a tested winning or executable rule.

| Fixed group | Decisions / games | Modeled costs | Direct model >=5pp | Direct strict last-20 >=5pp | Nondirect model >=5pp | Nondirect strict last-20 >=5pp |
|---|---:|---:|---:|---:|---:|---:|
| 13:30 UTC | 4 / 1 | 4 | 4 | 4 | 4 | 4 |
| 17:00 UTC | 36 / 8 | 36 | 30 | 23 | 29 | 22 |
| Observed subtotal | 40 / 9 | 40 | 34 | 27 | 33 | 26 |

For the larger group, the direct-mode mean one-contract cost was 53.50 cents;
the model mean net margin was 12.73 points and the strict prior was 9.59.
The later asks alone had yielded 35 versus 24 five-point margins. Fees reduce
both counts and leave the same-model versus simple-control question for actual
outcomes. The first group's diagnostic was calculated after its 13:30 kickoff
but uses only previously captured receipts and no results. The 17:00 group
diagnostic was generated at **2026-10-04 16:03:00 UTC**, before kickoff. Its
remote commit provides an additional pregame chronology marker.

Ignored local outputs (SHA-256 hashes are of the report files, distinct from
the evidence-body hashes in each report):

- `.local/stat-only-prelock-net-prior20-20261004T1330.json`:
  `fd883680ed1d0becc151c1a62003c48362590bcd90a46817f2491fd9d1f9e841`
- `.local/stat-only-prelock-net-prior20-20261004T1700.json`:
  `a5e4bea1b5a3bba765aff3cd6672bd902bbb89d0731f594d7612a288b3bf768b`

Byte-identical ignored backups are in the original workspace under
`.local/stat-only-prelock-net-prior20-20261004-backup/`.

The reports keep all fixed group candidates in their denominators, including
missing fee/quote evidence. The remaining 30 of 70 original decisions belong
to four later kickoff groups. These reports assume one hypothetical fill at
each displayed ask; no fill, result, ROI, CLV or consumer edge is verified.
Shared players/games make individual contracts dependent. Even after the
October 6 full venue-result gate, this first 15-game cohort cannot satisfy
the frozen 50 independent paired-game skill gate.

The separate **full-70 rollup** validates all six fixed kickoff scopes and
the original fee-cohort audit, runs this same strict-control comparison only
where both independent receipts exist, and retains every missing candidate.
After the first two groups it reports 40 modeled costs, 30 missing, direct
five-point net-margin counts 34 model versus 27 strict prior on the explicitly
labeled **modeled subset**. Its full-cohort margin fields are `null` until all
70 costs can be modeled. Mean direct modeled-subset net margins are 13.92 and
10.72 points, respectively; these are forecasts, not measured returns. The
ignored output is
`.local/stat-only-prelock-net-prior20-cohort-after-second-20261004.json`,
SHA-256 `1aa228ee0a460c27dc14b3715442f129dfc53b2b353f91d4af895303e06f83cd`,
with a byte-identical ignored workspace backup.

Run the same offline diagnostic only against an already captured group's
existing receipts, with a new exclusive output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prelock_net_prior20 `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --control .local/kalshi-stat-only-fixed-prior20-control-20261004.json `
  --fee-receipt .local/stat-only-prelock-fees-20261004T1700.json `
  --quote-receipt .local/stat-only-prelock-20261004T1700.json `
  --output .local/stat-only-prelock-net-prior20-20261004T1700.json
```

No paid sportsbook API, card, purchase, bet, result lookup or provider quote
request was used for this diagnostic.

For subsequent naturally captured groups, use the fixed-70 rollup with a new
exclusive ignored output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prelock_net_prior20_cohort `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --control .local/kalshi-stat-only-fixed-prior20-control-20261004.json `
  --receipt-dir .local `
  --output .local/stat-only-prelock-net-prior20-cohort-new.json
```
