# Pregame fee metadata checkpoint for the frozen NFL paper cohort

The eight precommitted NO receptions decisions have original displayed asks,
but the archived event fee contexts were 11.45 hours old at decision time.
They cannot support a fee-adjusted profit claim. This new private,
outcome-blind checkpoint records contemporaneous public fee metadata for
the **original 70 fixed paper candidates** before each kickoff group's
prelock quote check. The eight remain a subgroup of the 70; no selection,
model probability, side, threshold, or original price changes.

The fee-only collector replays the pinned pair, market, forecast, quote,
decision, source, and schedule evidence before any request. It binds each
candidate to the archived exact ticker, event, and series. For the six fixed
kickoff groups there are 4/36/5/15/6/4 candidates and 2/14/2/6/2/1
distinct fee events (27 total). It requests only public series metadata,
series fee changes, and event fee changes through an unsigned reader that
raises if authentication is attempted. It requests no market quote or
order endpoint. Raw public responses, their compact fee projection, source
hashes, collection times, and two-host clock proof are retained under
ignored private `.local/` paths. A failed or unsupported fee endpoint leaves
that event explicitly unavailable. Existing output paths prevent a rerun.

Six one-time limited-user Windows tasks were registered two minutes before
the corresponding prelock quote tasks: 2026-10-04 at 12:13, 15:43, 18:48,
19:08, and 23:03 UTC; 2026-10-05 at 22:58 UTC. They need a logged-in,
powered-on workstation and remain scheduled observations, not guaranteed
receipts. The earliest task was verified Ready before its 12:13 UTC trigger. An early
invocation replayed the pinned inputs, refused the out-of-window call with
exit 2, and created no receipt or report.

The separate code and four focused tests verify identity, timing, raw-to-
projection consistency, endpoint failure retention, and mutation rejection.
A fee receipt alone cannot prove a quote was executable. After each
natural prelock quote receipt arrives, compare quote and fee timestamps
within five minutes, fee waivers, exact market identity, and displayed depth
before calculating any hypothetical single-contract cost. Keep missing
fee or quote evidence in the original denominator. Actual fills,
funding/FCM charges, venue settlement, ROI, CLV, qualified picks, and
a repeatable edge remain unverified. No Odds API credits, key purchases,
card charges, wagers, or redundant quote collections are involved.


## Offline join when both natural prelock receipts exist

`sportsbet.quant.kalshi_stat_only_prelock_fee_score` validates both separate
receipts against the same frozen candidate group. It compares each original
ticker to its later exact market, requires an open quote with at least one
displayed contract, rejects an active or malformed fee waiver, and requires
the fee context to have arrived before the quote request and remain valid
through quote receipt. Fee changes between capture and quote, a missing
market, missing fee metadata, and an invalid quote each keep their own
unavailable state in the fixed denominator.

For eligible rows it computes only a hypothetical **single-contract taker
cost** at both direct and nondirect balance precision. It reports subset
costs, a full-group total and conditional binary break-even win count only
when every original candidate is priced, and a digest of the private
per-contract cost rows. There are no fills, measured returns, or inferred
outcomes. The full 70-candidate series must still be audited across all six
groups and eventually matched to venue-authenticated results.

After the first naturally scheduled fee and quote tasks, run with a **new**
ignored output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prelock_fee_score `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --fee-receipt .local/stat-only-prelock-fees-20261004T1330.json `
  --quote-receipt .local/stat-only-prelock-20261004T1330.json `
  --output .local/stat-only-prelock-fee-scenario-20261004T1330.json
```

Focused offline tests cover a complete one-contract scenario, missing fee,
missing quote, fee arriving after the quote, active or malformed waiver, and
mutated raw or quote receipts. This scorer makes no network request.

Before the first scheduled capture, an integration test replayed two
individually valid synthetic receipts within the T-90 to T-70 window but six
minutes apart. The existing shared `fee_terms` gate correctly classified the
candidate `fee_changed_or_stale`, withheld the full-group cost and withheld
the conditional break-even count. This verifies that the stated five-minute
fee-to-quote requirement applies inside the original frozen scorer; no new
scoring version or model change was needed. Adjacent fee, scenario and cohort
tests passed **16/16**. No source or quote request was made by the test.

## Six-group frozen-denominator rollup

`sportsbet.quant.kalshi_stat_only_prelock_fee_cohort` replays the original
pinned pair/market/forecast/quote/decision/schedule evidence and requires the
same 70 candidates in the same six kickoff groups. It reads only the existing
private fee and exact-ticker prelock receipts from `.local/`. Missing fee,
quote, or both receipts keep every candidate in the fixed denominator.
Present receipts must pass their original raw-source, clock, identity, and
chronology verifiers; a receipt from another kickoff fails hard. The combined
report includes per-group states and conditional single-contract direct and
nondirect binary break-even win counts only when all 70 costs are modeled.
It does not collect data, infer fills or outcomes, calculate ROI/CLV, or
qualify consumer picks.

After the naturally scheduled tasks, run with a **new** ignored output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prelock_fee_cohort `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --receipt-dir .local `
  --output .local/stat-only-prelock-fee-cohort-after-capture.json
```

An offline replay before any scheduled captures passed the full original
preflight and reported the expected group counts 4/36/5/15/6/4, zero matched
fee-and-quote pairs, all 70 candidates as `both_receipts_missing`, and null
full-cohort cost, break-even, ROI, and CLV. That ignored report is a missing
source checkpoint, not a negative result. Three targeted rollup tests cover
missing groups, one-sided receipts, cross-group reuse, complete modeled costs,
and altered candidate scope.

## Conditional fee-aware paper result after venue settlement

`sportsbet.quant.kalshi_stat_only_prelock_paper_result` is a separate,
post-result, no-network audit of the **same 70 frozen decisions**. It verifies
the full pinned preflight, then recomputes all six fee/quote group costs from
original raw receipts. After the full 452-contract venue capture exists, it
checks the outer record commitment, expected 452-contract scope, full-cohort
postgame time gate, two-host clock identity, and all 452 exact venue result
states. Missing or invalid outcomes remain in the original 70-decision
paper denominator.

The post-result reader also replays both HTTP Date observations: uncached 200
responses, chronological requests of at most two seconds, recorded round trips
and local clock offsets, each offset within two seconds and the two offsets
within 1.5 seconds. A recomputed record hash alone cannot make a malformed
clock proof count as verified result evidence. This remains an unsigned clock
check, not a cryptographic timestamp.

It reports an observed-subset win count with its explicit denominator. It
reports the full 70-decision win rate only if all 70 venue outcomes verify.
It reports full-cohort *hypothetical one-contract* direct and nondirect profit
at the **later prelock displayed asks** only if every outcome and every fee/
quote cost verifies. A later quote cannot replace the original decision-time
ask. No fill, actual ROI, CLV, repeatable edge, or consumer qualifier is
inferred. A single correlated slate cannot establish a 75% live hit rate.

After the natural 2026-10-06 settlement task, use a new ignored output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_prelock_paper_result `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --receipt-dir .local `
  --settlements .local/stat-only-settlement-20261006.json `
  --output .local/stat-only-prelock-paper-result-after-settlement.json
```

A real frozen-input dry run before the gate exited 2 *before reading the
settlement path* and wrote no output. Four targeted tests cover complete,
missing and altered result/cost denominators, capture gate and record hash.
The capture test also rejects cached, failed, inconsistent, and out-of-bound
clock observations after a record hash is recomputed. The focused clock,
prelock, settlement and paper-result suites pass 19/19. No provider call or
result was obtained by the dry run or these tests.

## Pregame clock type hardening before fixed fee/quote tasks

The shared prelock clock verifier is used by both one-time public fee metadata and exact quote captures. Its recorded RTT, offset and HTTP Age previously allowed JSON booleans to compare equal to numeric zero or one. A receipt with a recomputed evidence hash could therefore carry a fabricated boolean timing field. The verifier now requires exact finite numeric RTT/offset types and an explicit absent or zero Age of the expected type. The separate context-refresh verifier applies the same Age rule before reading release metadata and during replay. This does not change the fixed task trigger, 90-to-70-minute window, requested tickers, fee scope, model or 70-decision denominator.

Synthetic self-hashed boolean RTT, offset and Age mutations now fail. Focused prelock/fee/context tests 17/17; full backend 2,082 passed/72 skipped with seven existing warnings. No free public quote or paid odds request was triggered by the tests. The natural first fee/quote tasks remain scheduled for 12:13/12:15 UTC.

## Pregame clock freshness before the first fixed captures

The common fee and exact-quote capture/replay verifier now requires the two-host
clock proof to precede the first market request by no more than 120 seconds.
Previously a self-hashed, otherwise coherent proof from the start of the
20-minute T-90 to T-70 window could be reused near the end. A synthetic proof
with every host timestamp shifted back together and a recomputed record hash
now fails replay; immediate proof still passes. The six fixed task windows,
70 frozen decisions, provider request scope, quotes, prices and fees are
unchanged. No additional provider request was triggered by this check.

## First natural Oct 4 13:30 UTC kickoff group

Windows tasks `SportsbetStatOnlyFees20261004T1330` and
`SportsbetStatOnlyPrelock20261004T1330` ran at their fixed 12:13/12:15 UTC
triggers and each returned `LastTaskResult=0`. They used the unsigned public
read-only path, not the paid Odds API or a venue trading key. Original raw
receipts/reports were byte-matched to ignored backups under the workspace's
`.local/kalshi-stat-only-prelock-20261004/`; no repeat request was made.

| Original ignored artifact | File SHA-256 |
|---|---|
| Fee raw | `257c325e77d86f1045807dd9cb7e9bb80caae95e23c391d7c3e731c7452890c4` |
| Fee report | `d1be50d45dcdfc6d43e66d0b207909b9b89e5d31cdc12d36074c659f1a17b01f` |
| Exact-quote raw | `671e998b04669fab7475edf40615c0e1d2163b3c25bbdbb80420bb0c11ab47bc` |
| Exact-quote report | `88874e710256291c1b029344dcefcfb9563a33a0920457ae9bc8a15696c44b64` |

The fee receipt's record digest is
`768af884afa1d4cb7526eb1e545d3fa9c245ff5a7dcf6a56ae18416d3288aa34`;
the quote receipt's is
`c80822fd298b3b0c8e2b9960529f2c770b203b7483b061394fbb40a01a569b8c`.
Both original verifiers and the full pinned preflight passed in separate offline
fee/quote and 70-candidate rollups. The two-host clock proofs were checked at
12:13:06.220593 and 12:15:05.271794 UTC, immediately before each venue read.
The two fee contexts were received by 12:13:06.769620; the exact quote page
was requested 12:15:05.475899 and received 12:15:05.704475. This satisfies
the original five-minute fee freshness and prelock timing checks.

For the first **4 frozen candidates in 1 game**, both fee events were observed,
all **4/4** later exact asks had the original identity and at least one displayed
contract, and the asks moved up for two and down for two. The mean chosen-side
ask change was **+0.0025** dollars per contract. The separate one-contract
fee scenario modeled a total direct cost **$1.7377** and nondirect cost
**$1.75** across four hypothetical buys; at least two binary wins would exceed
either cost. Its ignored output file hash is
`de18d7618af97981b1abb6f1cab545d6d6efcacf039127010c9abff32ad246e9`.

The six-group offline cohort retained **4 modeled / 70 fixed** decisions and
**66 not yet captured**, with full-cohort cost and break-even still null; its
file hash is `379956e78aba5b2de3fbefa4a840f8535b3f1ed3eb88b64359de7083bc8df06c`.
The ask-movement rollup likewise has 4 exact asks and 66 `not_yet_due`; its
file hash is `7eaf55683e149131541303f6bd0d9085867fb0f13d5063077474a796302778fb`.
The remaining fixed fee/quote tasks must run at their own windows. No outcome,
fill, actual return, CLV, repeatable edge, or qualified consumer pick is
established by this single-game price observation.
