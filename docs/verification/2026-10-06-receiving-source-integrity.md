# Receiving source integrity before forward NFL collection

## Demonstrated gap

The complete-week v1 gate checks scheduled dates and that all expected teams
have statistics and snaps. Removing a receiver's nonzero row from a team that
still has its quarterback does not change that team coverage. Such a partial
feed can look current while omitting recent receiving performance. Snap-backed
zero sensitivity would then be unreliable for the omitted player.

An offline reproduction used the original hash-verified October 3 assets and
schedule, not a new feed or later outcomes. The original week-3 gate accepted
both the complete source and a copy in memory with one receiver row removed:
**32 stats teams, 32 snap teams, 16 schedule games** in both cases. The new
accounting check accepted the original and rejected the partial copy. No raw
source file was changed.

## Forward repair

`kalshi-nfl-stat-only-receiving-source-integrity-v1` checks every retained
regular-season team/week in the existing 2024–2026 player assets:

- Total player completions must equal total receptions; total passing yards
  must equal total receiving yards within the same season/week/team.
- Counts must be explicit finite nonnegative integers. Yardage must be an
  explicit finite signed integer. Nulls do not become zero.
- Multiple passers and trick plays are included regardless of position.
  Negative passing/receiving yardage remains valid. Lateral recipients may
  contribute yards without a reception; yard reconciliation catches their
  omission even when reception counts still balance.
- Duplicate player/team/game rows are rejected. The retained feed has **40
  anonymous rows with explicit zero passing and receiving statistics**. Those
  placeholders are excluded from player evidence, cannot establish a team's
  coverage, and cannot carry nonzero or missing statistics. Duplicate anonymous
  placeholders in the same team/game are rejected.

The accounting follows the [NFL Guide for Statisticians, Passing and Laterals
sections](https://www.nflgsis.com/gsis/documentation/stadiumguides/guide_for_statisticians.pdf):
the forward catch gets the reception, while a subsequent lateral can add
receiving yards without another reception. The retained nflverse schema has
explicit integer columns for these four fields, consistent with the
[player-stat loader](https://nflreadr.nflverse.com/reference/load_player_stats.html).
The 1,186-game reconciliation below is additional empirical verification;
it is not a substitute for source chronology or individual player identity.

New capture actions run this check **before public market or exact-quote
collection**, after the existing freshness gate. A private
`source-receiving.json` retains source hashes, counts, observation time and the
normalized implementation hash. The pregame commitment and existing private
server marker bind its raw hash. Publisher/result replay reconstructs the
check from the exact manifest-authenticated bytes and rejects changed,
removed, retrofitted or late receipts. Reads are bounded, links are refused,
and Parquet parsing uses the same bytes that passed hash/size verification.

This is an additional forward intake check. The original freshness v1 code,
model, 5-point replication rule, qualification thresholds, original October 4
selection and results remain frozen. Legacy commitments with no receiving
receipt still replay under their original checks. No consumer recommendation
is promoted by this source report.

## Retained-data verification

All **40,077 regular-season source rows** were checked: **40,037 identified
player rows** plus the 40 excluded anonymous zero placeholders. Both count
and yardage accounting match for **1,186 team-games**:

| Retained season | Team-games | Count mismatches | Yardage mismatches |
| --- | ---: | ---: | ---: |
| 2024 | 544 | 0 | 0 |
| 2025 | 544 | 0 | 0 |
| 2026, original pregame snapshot | 98 | 0 | 0 |

The ignored final reproduction report is
`.local/receiving-source-integrity-verified-20261006.json`, SHA-256
`59466251a6a718532ba86fe48fd8a72adfbada76a10ddc2a594cebf9dde5c027`.
It binds source manifest
`c0b2efdc87f4ddb15222c1ba06145d16d401dfaef98b8131c42e3a62f7b122a6`
and implementation
`5c50bc5bef9a980af1b3d6a52b30eb27e07d93e673108c9968dd28399e35abca`.
The original three stats asset hashes are unchanged. The source observation
is the retained October 3 09:14:06.503788 UTC staging time; this does not claim
that those old assets satisfy the next October 8 current-week requirement.

## Limits and next checkpoint

Verification: **75 focused source/capture/commitment/publisher/result/series/
remote-anchor/launcher tests passed**. They reproduce missing receiver and
lateral rows, null/boolean/fractional/nonfinite statistics, negative counts,
multiple passers, valid negative yardage, duplicate identities and anonymous
placeholders. Capture regressions stop before market/quote reads. Receipt
regressions reject late, changed, removed and retrofitted evidence while
preserving legacy replay. Cached pinned Bandit passed for changed Python.
The original frozen model/results and both preserved pregame refs are unchanged.

Balanced totals are necessary, not sufficient, for complete player coverage:
omitted zero-stat players or balanced missing passing/receiving rows can still
escape this check. Existing roster, source cutoff, player binding, snaps,
availability and qualification gates remain necessary. This guard does not
prove a higher win rate or explain the October 4 model's calibration error.

At **October 8 17:25 UTC (10:25 AM Pacific)**, inspect the existing capture
and publisher. In addition to the retained schedule, week-4 freshness,
context and recent-gap receipt, verify `source-receiving.json`, its pregame
commitment hash and private server-dated anchor before kickoff. The PC must
be on and logged in. Failed/missed pregame attempts cannot be backfilled
after kickoff. No extra scheduled job or provider request was introduced.
The production CI account gate and $0 spending restriction remain unchanged.
