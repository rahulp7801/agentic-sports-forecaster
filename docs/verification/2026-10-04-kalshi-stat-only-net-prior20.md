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

## Third natural kickoff group, October 4 at 20:05 UTC

The original one-shot Windows fee and exact-ask tasks ran at 18:48 and 18:50
UTC and both returned `LastTaskResult=0`. They observed two fee events and
matched all five original decisions in one game to later exact asks. Four asks
rose, one was unchanged, and the mean chosen-side ask movement was +0.0080
dollars per contract. Raw files and reports were copied byte-identically to
the ignored D-workspace `stat-only-prelock-20261004T2005-backup/` directory.
The raw fee receipt was recorded at 18:48:07.645069 UTC after a two-host
clock check at 18:48:07.117949; the exact-ask receipt was recorded at
18:50:05.409243 after its clock check at 18:50:04.944329. Both original
verifiers and the fixed-source replay passed before the 20:05 kickoff.

| Retained file | SHA-256 |
|---|---|
| Fee raw | `adc5aead76a4fbda1ec9f0c0c8cebbb85380eb3c5316bba3715256f728efdb31` |
| Fee report | `cb1a4ae994b5310f01a1394f6ce1ba676f02e5790750cad2f415ad01a4d1ecb1` |
| Exact-ask raw | `93c9709fba4366d51fca15b5e0083ef758c4cee247a6b38798fbb92eed7dd466` |
| Exact-ask report | `f0dcf41a273d807d1eec43c6d5cbfb052fae94a126d075294f30faf3c5f1a646` |

The existing offline fee-aware strict-last-20 scorer authenticated the same
five original decisions, modeled one hypothetical contract per decision, and
found a direct-mode net margin of at least five points for **5/5 model and
5/5 strict-last-20** estimates. This group therefore does not separate the
model from that simple control. Its private diagnostic SHA-256 is
`30668ad9a18f7734e4f1001282f64630afbf2c0de6bd95c266431b48ab8576d8`.
The fixed-70 rollup now has **45 modeled costs / 25 missing**, with direct
five-point screens **39 model versus 32 strict-last-20** on the explicitly
labeled modeled subset. Every full-cohort margin stays null; the report SHA-256
is `1bd9254f48822e643aa3b293eba238aee9a2d713dd59e573a6bbe68abfca2d22`.
All seven additional model screens at this point come from the 36-decision
17:00 kickoff group: the other two observed groups are 4/4 versus 4/4 and
5/5 versus 5/5. This concentration is a warning against interpreting the
45-row subtotal as replicated game-level advantage.
These are outcome-blind displayed-ask and modeled-fee scenarios, with no fill,
win, actual return, or established edge.
Three of the separately fixed eleven model-probability-at-least-75% paper
decisions belong to this 20:05 group; two belong to the next 20:25 group.
This is a pre-result coverage mapping, not a new selected subgroup.

The separate existing fixed-70 ask-persistence replay covers **45 exact later
asks across 10 games**: 13 chosen-side asks rose, 13 fell, and 19 were
unchanged. The observed-subset mean ask movement was +0.000667 dollars per
contract; 15 decisions had an open future capture window and ten were not yet
due. It does not label either category as a failed quote or a win. Its ignored,
byte-backed report SHA-256 is
`4351ce1583f234941b00b265cc3abba35b587c797d108d55254d9add726014f4`.
This is a later displayed ask check, not closing-line value or a fill.

## Fourth natural kickoff group, October 4 at 20:25 UTC

The original one-shot fee task ran at 19:08 UTC and the separately scheduled
exact-ask task at 19:10 UTC. Both returned `LastTaskResult=0`. The fee source
reported six observed events for the fixed **15 decisions across three games**.
All 15 later asks matched exact original decisions: seven rose, five fell and
three were unchanged, with a zero contract-weighted mean movement. The fee
receipt was recorded at 19:08:06.887775 UTC after its 19:08:06.201813
two-host clock check; the quote receipt at 19:10:05.818003 after its
19:10:05.358237 check. Both precede the 20:25 kickoff. The raw files and
reports were copied byte-identically to the ignored D-workspace
`stat-only-prelock-20261004T2025-backup/` directory.

| Retained file | SHA-256 |
|---|---|
| Fee raw | `1696aff4e37fa640c8a0ad48ee559a7ea951e9ad858c060130e599c6339067f4` |
| Fee report | `d8de6aa0bd70b9d9235a787f3220ae92d043d837865d9be06259cc67c0bfe961` |
| Exact-ask raw | `1451f51923088cc07458b149113f892a9cfbc8b109fbd7a0c2a2c220056e6608` |
| Exact-ask report | `e767c9789fd80b632bf5d7014aa96bfdaf8494b946c6bcd14f0f20de19d69e30` |

The existing offline strict-last-20 scorer authenticated all 15 fee/ask
costs. In direct mode, a modeled net margin of at least five points survived
for **11/15 model and 11/15 strict-last-20** estimates. The group diagnostic
SHA-256 is `9b8d3633f8c39e4d8575143de49679af51bf36cf320999e487e5fabe881efe31`.
The fixed-70 rollup now has **60 modeled costs / 10 not yet captured**; its
direct five-point modeled-subset screens are **50 model versus 43 strict**.
All seven additional model screens remain concentrated in the earlier 17:00
kickoff group. Full-cohort fields are still null. The report SHA-256 is
`1faad5ce79d850ae5c01857e829456e87acc69139b9aed780b9d315a471198a3`.

The fixed-70 ask-persistence replay now covers **60 exact later asks over 13
games**: 20 rose, 18 fell and 22 were unchanged. The observed-subset mean
movement was +0.0005 dollars per contract; the other ten decisions are
`not_yet_due`. Its report SHA-256 is
`610c00a72f271ed34757a5c628171c221105a0927373361df6baf2f41ed42e5b`.
All eleven original model-p>=75% decisions now have a later fee/ask receipt,
but none has an authenticated outcome or verified fill. These displayed-cost
scenarios cannot establish a 75% win rate, profit, or executable edge.
