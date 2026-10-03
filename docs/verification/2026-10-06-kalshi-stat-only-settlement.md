# One-time exact NFL stat-only settlement capture

The October 4 paper cohort remains fixed at **452 exact Kalshi contracts**,
**144 stat-only model forecasts**, and **70 paper ask-policy decisions** (11
original model-p>=0.75). The independent frozen preflight reproduced these
counts offline on October 4. Its last scheduled game begins October 6 00:15
UTC; the existing result collector refuses to query until **October 6 06:15
UTC**, six hours later. No actual outcome is known from this preflight.

A one-time local Task Scheduler job, `SportsbetStatOnlySettlement20261006T1400`,
is scheduled for **October 6 14:00 UTC** (07:00 Pacific), after the full-cohort
gate. It reads at most **23 public GET batches of 20 precommitted exact
tickers** via the [public exact-ticker market endpoint](https://docs.kalshi.com/api-reference/market/get-markets). Its reader explicitly
refuses authenticated headers. It has no order method, no Odds API call,
no API key use, no paid credit, and no bet. No extra contract can enter the
cohort.

A malformed successful public page (for example JSON `null`, an array,
or a non-list `markets` field) now fails aggregate validation as an explicit
unavailable audit after the bounded raw receipt has been assembled. It cannot
silently grade an outcome or abort before the raw capture is saved. No retry
or additional venue request is introduced by this audit correction.

The request leaves the optional status filter empty so closed or finalized
contracts remain visible for explicit grading. Each missing, unreturned,
nonbinary, invalid or provider-failed result remains in the 452-contract
denominator. A later authentic venue result may require a separate audit; this task does not retry or manufacture a result.

Before the first market request, the wrapper replays the pinned pair, original
market archive, source manifest, model, quote and decision receipts, checks the
452-contract denominator, and requires the full postgame gate. A two-host
public HTTP Date check provides prospective clock evidence. The exact receipt
is bounded to 30 MB, written exclusively under ignored private `.local/`,
and its outer record hash binds the clock proof to the provider evidence. An
aggregate venue audit is written separately. If the venue payload cannot be
audited, the raw full-denominator receipt is still retained, the report is
marked unavailable, and the task fails. Raw player-level records stay out of
Git and must be backed up to the existing ignored workspace directory after
capture.

The scheduled action is:

```sh
python -m sportsbet.quant.kalshi_stat_only_settlement_capture \
  --pair .local/verified-timely-pair-20261003/pair.json \
  --market .local/verified-timely-pair-20261003/market-archive.json \
  --forecast .local/kalshi-stat-only-probabilities-20261004.json \
  --quotes .local/kalshi-stat-only-quotes-20261004.json \
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json \
  --source-dir .local/verified-timely-pair-20261003/sources \
  --schedule .local/team-share-sources/games.parquet \
  --output .local/stat-only-settlement-20261006.json \
  --report .local/stat-only-settlement-20261006-report.json
```

The task uses the current user's limited interactive principal, requests a
wake timer, runs only on AC, stops on battery, has a ten-minute execution
limit and no retry. It still requires the computer on and logged in. Check
its actual `LastTaskResult`, raw receipt and aggregate report after the
trigger; a Ready state before the trigger proves no result was collected.

Only after this receipt verifies should the already-frozen stat-only forward,
original >=0.75, lower-tail-calibration, and teammate-context diagnostics
score the same authenticated 452-contract result archive. Keep unverified
states explicit. Displayed asks are not fills, and this single correlated
slate cannot establish a repeatable 75% win rate or an executable price edge.
No consumer pick or model promotion follows automatically.
## Pre-result production and task checkpoint, October 4 06:10 UTC

Read-only public dashboard requests at this time returned zero current picks for
NFL, CFB, and NBA. The authenticated settled pick ledger reported NFL 4 wins / 4
losses (8 decisions), CFB 1 win / 1 loss (2 decisions), and no NBA decisions.
The latest NFL and CFB scans were stale since October 3 12:39 UTC: 14 and 54
eligible events respectively, all deferred for recorded rolling API allowance,
with zero completed scans or quotes. The production release did not advance:
exact private head `4573ae2df7cbba36421da92882b8b7736405b6ec` CI run
`37181883681` failed all five code jobs with zero steps; schema and deploy were
skipped. This is a hosted account billing/spending gate, not a passed code test.
No scheduled paid quote collection was triggered for this check.

The free, unsigned local context refresh is Ready/unrun for October 4 10:45 UTC.
The first exact-ticker prelock quote observation is Ready/unrun for October 4
12:15 UTC. The full-denominator result task is Ready/unrun for October 6
14:00 UTC; its receipt and report do not yet exist. After each run, inspect
Task Scheduler's actual last result and verify/back up its ignored raw receipt
before drawing any conclusion. Do not backfill a missed prelock price or treat
model probability, 5/10 past decisions, or an ungraded venue contract as a 75%
win rate or positive matching-price return.

## Postgame clock Age type check prepared before results

The shared two-host HTTP clock observer and the frozen-70 postgame capture
wrapper previously converted the recorded `Age` value with `int()`. A
rehashed JSON receipt carrying `false`, `0.0`, or a noncanonical zero string
could pass as an uncached observation. Before any Oct 6 outcome exists, both
paths now require absent Age or exact integer/string zero; the captured HTTP
header naturally supplies a string. Rehashed tampering with those values is
rejected by the wrapper. Focused clock, capture, paper-result and uncertainty
tests pass **22/22**. The original 452-contract scope, 70 fixed decisions,
selection, probability, fee/quote costs, result formula and collection window
are unchanged. No venue outcome or additional quote was requested by this
verification.

The scheduled unsigned collector also replays both hosts, typed RTT/offset,
uncached Age, local/server offsets and chronology **before** its first venue
result request. Previously it checked only the proof's boolean and timestamp
before network I/O, leaving the detailed proof to later replay. Mocked
invalid proofs now produce zero venue reads, even if their overall receipt
could later be rehashed. Focused clock/capture/result/uncertainty tests pass
**28/28**. The Oct 6 gate and 452-contract request scope are unchanged.

## October 5 scheduled-source and offline scoring handoff

The original collector intentionally still uses the retained Temp checkout.
Comparing the collector, shared clock observer and venue reader with the
durable private release found only Windows line-ending differences; the
frozen evaluator and venue-result verifier match. A rehearsal from the actual
scheduled working directory and copied Python environment replayed the
pinned source/model/quote/decision preflight, then refused the premature
October 6 06:15 UTC gate. It wrote no result and made no venue request.
The task's existing wake, limited interactive principal and battery settings
remain in place; its current power settings allow battery operation, superseding
the older AC-only description above.

The separate offline `kalshi_stat_only_fixed_score` handoff verifies the full
result wrapper's record hash, original 452-contract scope, postgame clock
proof and receipt chronology before calling the unchanged frozen primary
scorer. It refuses the time gate before opening any settlement file. Its
preflight-only mode replays original inputs without reading results or writing
a score. This wrapper adds admission checks; the fixed model, policies,
probability mathematics, original denominators and evaluation version remain
unchanged.

A limited interactive one-shot score task is scheduled **October 6 14:15 UTC
(7:15 AM Pacific)**, after the original collector's ten-minute limit. It uses
the durable verified source launcher and writes only the ignored private
`.local/stat-only-forward-after-result-20261006.json`. Missing or invalid
results fail; it cannot retry collection or invent an outcome. The collector
and score task still require this workstation to be on and the user logged in.
Their task exit codes and resulting receipts/reports must be inspected after
the triggers. No actual result has been read during this preparation.

The handoff and adjacent frozen-scorer/capture-wrapper/launcher suites passed
**14 tests**. The real preflight-only invocation from the durable copied
environment reproduced **452 contracts, 233 source-eligible contracts, 144
forecasts, 70 paper decisions and 15 games**, with zero authenticated results.
It confirmed the original October 6 06:15 UTC gate and wrote no score. Pinned
Bandit found no medium-or-higher issue. The score task is Ready at the exact
14:15 UTC trigger, with wake enabled and limited interactive privileges.

The existing `kalshi_stat_only_prelock_paper_result` now has a separate
limited one-shot offline task at **October 6 14:20 UTC (7:20 AM Pacific)**.
It uses the same verified local launcher, original pinned inputs, six fee/price
receipt groups and the exact authenticated result wrapper. It retains all 70
decisions and leaves full hypothetical fee-inclusive payoff null unless every
cost and result verifies. Actual fills, ROI, CLV and repeatable edge remain
unverified. This task makes no provider request and does not depend on changing
the primary scorer or replacing the original asks. Its real pre-gate CLI
rehearsal refused before opening the settlement file and wrote no report;
15 adjacent launcher/fee/result tests passed. The task is Ready at the exact
14:20 UTC trigger, with limited interactive privileges and wake requested.
