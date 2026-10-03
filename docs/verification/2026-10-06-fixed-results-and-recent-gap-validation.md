# First fixed results and independent recent-history validation

## Result recovery

On October 6 the three original result/score tasks reported terminal launch
refusal `2147946720` (`0x800710E0`), with no result files or live collector/scorer.
Windows recorded sleep from **11:10:44.3138 to 17:32:08.0315 UTC**, spanning
the original 14:00/14:15/14:20 triggers. The tasks' reported last-run time was
17:38:06 UTC. Sleep and the refusal were observed; the precise scheduler refusal
cause was not established. Task settings and triggers were not changed.

After confirming the jobs had not executed, the original durable collector
arguments were run once. The original preflight and two-host HTTP Date proof
passed. It completed **23 unsigned public result GET batches** for the original
**452 contracts**. The receipt's `captured_at` is
**2026-10-06T19:07:04.640633+00:00**, after the full result gate. No quote collection,
Odds API request, key, paid credit, order or bet was used. Both original offline
scorers completed, followed by the existing frozen diagnostics. The model,
candidate set, subgroup rules, thresholds and pregame price/fee inputs were
not adjusted after results.

## Prospective evidence

All 452 contracts remain in the result accounting: **445 verified binary and
7 nonbinary**. Of the 144 model forecasts, 140 have binary results. The original
70 selected paper candidates have **69 binary results and 1 nonbinary result**;
that last contract remains in the full denominator.

| Frozen scope | Wins / binary results | Contract win rate | Games |
| --- | --- | --- | --- |
| Original 70, verified binary subset | 39 / 69 | 56.52% | 15 |
| Original model probability >=75% | 8 / 11 | 72.73% | 8 |
| Original chosen-side model uplift >=5 percentage points over strict recent 20 | 15 / 23 | 65.22% | 13 |

The 11 high-probability picks average **80.14% frozen model probability**.
Their whole-game 95% interval is **50%–100%** for both contract and equal-game
weighting. Eleven picks across eight games do not establish a 75% population
win rate, and observed performance is below their mean model forecast.

On the original **139 same-price paired forecasts** across 15 games, contract
weighted Brier error is **0.256988 model versus 0.250707 market** (lower is better).
The equal-game model-minus-market difference is -0.000564, with 95% game
interval **[-0.033090, +0.030025]** and player interval crossing zero. Log-loss
intervals also cross zero. There is no demonstrated market advantage overall.

The separate strict recent-20 control has Brier **0.270359** on those same pairs.
Model-minus-strict-recent-20 game and player intervals are negative on this
slate. This is improvement over the recent-history baseline, not proof of
market alpha. The older primary report's field `paired_prior_brier` refers to
its broader retained history; it is not the strict last-20 control.

The already declared 23-pick uplift group has Brier **0.218371 model versus
0.262852 market and 0.228113 strict recent-20**. Its market comparison game
interval is **[-0.143876, -0.001544]**, but the player interval is
**[-0.137950, +0.002184]**, crossing zero. Its strict-recent-20 intervals also
cross zero. This is a promising research signal from 13 games, not an
established edge. Other predeclared diagnostics were also inspected.

The full fee-inclusive paper score remains **incomplete**, with full-cohort
win rate, both net profits and ROI null because of the nonbinary result.
All 70 pregame cost scenarios were covered; actual fills were never verified.
The original-ask verified-subset gross arithmetic (+4.2300 hypothetical units)
does not include fees or establish realized trading profit. All frozen reports
retain zero qualified picks and false edge/execution support.

## Evidence preservation

The durable result bundle is `.local/fixed-cohort-20261004`. Scores remain in
the private checkout's `.local/`. A second **9-file, 1,624,748-byte** copy was
saved under the outer workspace's ignored `.local/fixed-result-backup-20261006`.
Every destination hash matches its source. This is a second local copy on the
same drive, not an offsite backup. Its manifest SHA-256 is
`00e90bf4d6496225bf88175538675428cc1267d301574301d9e477fc63433b1f`.
Raw provider/player data and reports were not committed to Git.

| Evidence file | Raw SHA-256 |
| --- | --- |
| stat-only-settlement-20261006.json | b9182a80eb4431736250f8c1e6596d671d4fcddf75d2da7a5fd5987f4020346f |
| stat-only-settlement-20261006-report.json | ed9ba9ea838f42d0f980d8af9129f1958c2edb910be73818ddfb4fc590cf3472 |
| stat-only-forward-after-result-20261006.json | 7178dc991a8483883427ebadca31b375868ae2a2d1e704892ca6ec22cb84e631 |
| stat-only-prelock-paper-result-20261006.json | 3c82c2ef47ee377737285a0c0603b2056a24dabdc159b5875ebd50103ea206d7 |
| stat-only-high-probability-after-result-20261006.json | 3779c09fc841c94a4f112fa85c18dde54a7fbd355192b1e2e8e08ff264d3d2bf |
| stat-only-win-uncertainty-after-result-20261006.json | 6212546f67ffe72d16ed431e4786cfd7edf14f0aa5ffebc9be943291478b4e09 |
| stat-only-strict-prior20-after-result-20261006.json | 59948497de0d7f3e87f22f7eaadf4353e9f035cfb29cd80dd3fdfecf48853dc7 |
| stat-only-recent-gap-after-result-20261006.json | d5d7d735b87bea3ffe09f36fc77471543a51c9acca21f239cbbc6d3113573f11 |

The raw receipt's outer record commitment is
`093f1ab5c9aa5153e0022c9b689b65affe8a0c0b510734ecdbfdf9616c823dbc`;
authenticated result evidence is
`870239aff8a70237f70619a54fd732eafd8e5bec48da85742842f90c337a6981`.
The strict recent-20 control, now copied into the durable bundle, remains
`8b052035e6ebc3b4aaa27f00aea5d03e601cfd414e93fcaee9248634082fa3ff`.
The original 38-file input copy manifest and both preserved pregame refs are
unchanged. The October 5 23:05:19 UTC private server push still precedes the last
October 6 00:15 kickoff.

## Independent follow-up, fixed before its games

The first slate motivates testing the **same 5-point chosen-side uplift rule**
on new games. Choosing it for follow-up after seeing this slate is explicitly
acknowledged. October 4 does not enter the new validation sample.

`kalshi-nfl-stat-only-next-recent-gap-v1` starts at **October 8 17:00 UTC**.
Existing scheduled captures now write `recent-gap.json` alongside the original
forecasts, decisions and strict recent-20 control. It fixes the policy, exact
input-row commitments, evaluation implementation hash, and membership of both
uplift and other groups without reading results. The implementation binds this
evaluator, membership rule, primary series, loss and cluster helpers; only CRLF
line-ending normalization is permitted across checkout/staging. Changed
evaluation code requires a separate version/sample. The pregame commitment
includes the receipt's raw hash; the existing
private server-dated marker binds that whole commitment. Replay rejects changed,
removed or retrofitted receipts. Legacy cohorts remain available to their
original evaluator but cannot enter this new replication report.

The separate offline series evaluator reuses the existing source chronology,
model replay, authenticated venue results, retained schedule and private remote
anchor checks. The first server-published capture owns a whole fixture; missing
prices/results cannot be repaired by choosing a later overlapping capture.
All selected outcomes remain in the denominator. Replication support requires
complete matching prices/results, **50 independent paired games**, remote
pregame proof, and negative upper 95% game **and** player bounds for Brier **and**
log-loss against **both** market and strict recent-20. These are research
support gates; the report never enables consumer picks or asserts execution
profitability, even if they pass. The original model and selection policy are
unchanged.

After results, use a private manifest with protocol
`kalshi-nfl-stat-only-next-recent-gap-v1` and the same relative case-path schema
as the existing independent-series manifest (seven input paths, source_dir,
commitment, settlements, anchor_commit_oid, anchor_marker_path). Paths cannot
escape the manifest directory. Output is exclusive. From the durable checkout:

```powershell
.venv/Scripts/python.exe ops/run_paper_task.py --module sportsbet.quant.kalshi_stat_only_next_recent_gap --manifest .local/recent-gap-series.json --output .local/recent-gap-series-result.json
```

The evaluator does not collect quotes or venue outcomes. Its remote verification
only reads private GitHub timeline/ref evidence. No new scheduled job, task
setting, paid provider request or reserve change is needed for this increment.

## Next exact checkpoint

Verification for this increment: **52 focused capture/commitment/publisher/
result/series/remote-anchor/source-week/frozen-diagnostic tests passed**, plus
**4 durable launcher tests**. After adding the evaluator implementation
commitment, **23 receipt/rule/capture tests were rerun and passed**. They cover
the exact 5-point YES/NO boundary, motivating-cohort exclusion, duplicate and
altered input scope, changed/removed/retrofitted receipts, changed evaluator
code, full nonbinary denominators, earliest remote ownership, missing prices,
50-game and remote-proof gates, and both comparator/player uncertainty gates.
The actual durable CLI help succeeded without collection. Cached pinned Bandit
and the redacted staged Gitleaks scan passed. No frontend or broad backend
rerun is claimed for this offline research increment.

At **October 8 17:25 UTC (10:25 AM Pacific)**, inspect the existing capture
and private publisher exit codes. The subsequent
[receiving-integrity repair](2026-10-06-receiving-source-integrity.md) also adds
a pre-market passing/receiving reconciliation and `source-receiving.json` hash
to new attempts. Verify retained schedule/source/context,
`recent-gap.json` and its commitment hash, private marker server push before
first kickoff, and the preserved remote ref. The PC must be on with the user
logged in. A missed pregame capture remains unavailable; it cannot be backfilled
after kickoff. Future result scoring must wait for that cohort's own full gate.
Subsequent capture/publish pairs remain October 10, 17, 24, 31 and November 7,
at 17:00/17:25 UTC.

Private hosted CI remains blocked before runner steps by the account
payment/spending-limit gate; production remains stale. The $0 stop-usage budget,
required protection checks, unapproved PR #194, 20/450 credit limits and staged
reserve remain intact. Deployment and a statistically supported consumer edge
are still outstanding.
