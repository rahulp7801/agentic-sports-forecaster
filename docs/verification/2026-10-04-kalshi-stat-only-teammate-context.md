# October 4 NFL stat-only teammate-context checkpoint

This is an **outcome-blind paper diagnostic**, frozen at 2026-10-04 05:16:44 UTC
before the first 13:30 UTC kickoff. It does not change the frozen model, the
70 ask-policy candidates, the 11 original model-probability >= 0.75 subset,
qualifying thresholds, dashboard picks or orders. The private, ignored receipt
has semantic SHA-256
`0fce75d466db103ace59f5adf4034c1e5a60e2fad6795d28a57eec51c269b31a`
and file SHA-256
`733dc3f4a1b4d5fc85aeb32ce5f8117d264976e33a1f51933da883735484c792`.
It and the raw source are backed up in the local ignored prospective directory.
Only aggregate counts are tracked in Git.

## Source and definition

The [nflverse 2026 injury asset](https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.parquet)
was updated at the asset level on 2026-10-03 12:26:57 UTC; its pinned file
SHA-256 is `0d1ff127705c932b52ad4719f330cc314cfa2ef968d2abe426c5f6bc0f03228f`.
It contains 313 week-four report rows across 32 NFL teams. Its rows do **not**
contain per-player modification times. Therefore this is a dated archive
snapshot, not proof that every listed status still held at kickoff. An absent
player row means "not listed," not "active." The
[pinned 2026 player-week stats asset](https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet)
has SHA-256 `e95d60d7d9572a11032dca70a434b104636ee94f899091b810f71057b65a5d58`;
only regular-season weeks 1-3 contribute to context. The player's most recent
prior team connects the frozen GSIS forecast to the injury snapshot, so a
post-snapshot trade or roster move is a remaining identity risk. The frozen
market/model preflight already verifies the venue-to-GSIS crosswalk.

For each candidate, count same-team QB/RB/FB/WR/TE teammates listed `Out` or
`Doubtful`, exclude the forecast subject, and divide those teammates' combined
weeks 1-3 targets by that team's total weeks 1-3 targets. Predeclared bins are
zero, (0%,10%], (10%,25%], and >25%. With no such acute teammate, keep
`Questionable` separate from no reported skill-teammate risk. Missing team,
report or positive team-target denominator stays `coverage_unavailable`. The
three anonymous zero-target source rows cannot affect either numerator or
denominator and are skipped. Subject report status and acute quarterback flags
are retained in the private receipt, not promoted into an effect estimate.

| Pregame stratum | All 70 paper candidates | Fixed 11 high-probability subset |
|---|---:|---:|
| Acute teammate, >25% prior targets | 7 | 5 |
| Acute teammate, (10%,25%] | 3 | 1 |
| Acute teammate, (0%,10%] | 14 | 1 |
| Acute teammate, zero prior targets | 5 | 0 |
| Questionable teammate only | 15 | 1 |
| No reported skill-teammate risk | 26 | 3 |

This is a hypothesis check for overconfident `NO` forecasts when a major
teammate is absent, **not** a causal adjustment or evidence of profitable
prices. The high-probability subset is 11 contracts across eight games; team
and player results are correlated. Do not select a favorable bin after
outcomes and claim a 75% hit rate. No historical 2025 injury as-of replay is
claimed: the available 2025 archive was updated after that season.

## Next authenticated checkpoint

At or after **2026-10-06 06:15 UTC**, replay the exact 452-contract venue
settlement archive through the frozen evaluator and score this pinned context
receipt. Keep all 11 original high-probability candidates, count unverified
contracts and games, and leave full-group win rates/Brier/gross unit profit
null until each group's venue outcomes verify. Compare to each candidate's
original displayed ask, then later to prelock asks where a timely exact quote
was actually observed. Displayed asks are not fills; no fee-adjusted ROI,
closing-line value, consumer qualifier, or edge can be inferred from this
snapshot. Do not spend credits or collect redundant paid odds to fill gaps.

Local replay uses `python -m sportsbet.quant.kalshi_stat_only_teammate_context`
with the same `--pair`, `--market`, `--forecast`, `--quotes`, `--decisions`,
`--source-dir`, and `--schedule` paths as the prelock runbook, plus
`--injuries .local/nfl-injury-source-audit-20261004/injuries_2026.parquet`.
For post-result scoring, pass `--receipt` pointing to the ignored pre-result
JSON, `--settlements` to the authenticated exact-contract archive, and a new
exclusive `--output` path under `.local/`.

## Independent current-week roster cross-check

A separate, pregame audit at **2026-10-04 05:29:01 UTC** replayed the pinned
context receipt and joined its frozen GSIS forecast IDs to the
[nflverse week-level 2026 roster asset](https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2026.parquet).
The release asset was last updated **2026-10-03 12:30:28 UTC**, before first
kickoff; its GitHub-published and locally verified SHA-256 is
`4792e44d65e6df9b56e39cb4c16d172e08175a2e6a9daf25cfb718b0d0533bbf`.
The independent audit is `kalshi-nfl-stat-only-week4-roster-audit-v1`, record
SHA-256 `c5fdddf9e275c06b5a68e57772c87892ef3b8b57181ad8d502d682a09f169ab9`,
file SHA-256 `001d633f13085dace24f323690c14295b84406b80517796b71c2f0e7d5243326`.
Its raw asset and receipt are local, ignored and backed up; the tracked report
contains aggregate counts only. Exact offline replay reproduced its receipt.

The week-four roster contains 2,576 rows across all 32 teams; one practice
squad row lacks a GSIS ID and is explicitly excluded from the identity join.
All **70/70** fixed paper subjects, and **11/11** high-probability subjects,
match the same team in the week-four roster with status `ACT`. Across the
candidate teams, 19/20 distinct skill teammates reported Out/Doubtful are
marked `ACT` in that roster and one has another roster status; in the eight
high-probability-game clubs, the split is 9/10 `ACT` and 1/10 other (reserve).
The [nflverse roster-status dictionary](https://nflreadr.nflverse.com/articles/dictionary_roster_status.html)
defines `ACT` as **on the active roster**. It does not confirm game-day active
status, snap share, the final injury designation, or a causal target change.
This corroborates current-team identity at the archive timestamp but does
not replace the live consumer roster and injury gate or justify publishing a
pick. The original context strata and forecast probabilities remain frozen.

Replay from the private repository root with
`python -m sportsbet.quant.kalshi_stat_only_roster_audit` and the context
arguments above, adding `--roster .local/nfl-injury-source-audit-20261004/roster_weekly_2026.parquet`,
`--context-receipt .local/kalshi-stat-only-teammate-context-pre-result-20261004.json`,
and a new exclusive `--output` under `.local/`. No paid sports quote or
prediction was collected for this audit.

## One later free context snapshot

`kalshi_stat_only_context_refresh` is a **separate** one-time re-observation,
predeclared before any selected kickoff. Its only collection window is October
4 **09:30–11:30 UTC**; the local task is set for **10:45 UTC** (03:45 Pacific).
It first checks two independent public HTTP clocks, then reads the public
`injuries` and `weekly_rosters` GitHub release listings. Each exact 2026 asset
must have the expected name, canonical public URL, uploaded state, bounded
size, SHA-256 digest and an update time after or equal to the original pinned
asset but before the observation. An unchanged hash reuses the original local
bytes; a changed hash triggers one bounded public asset download. The output
is an exclusive ignored directory containing the two files, release metadata,
source hashes, request chronology and a receipt hash. There is **no** Odds API
call or price collection in this task. A failed or missed run remains missing;
no postkickoff fetch may masquerade as a pregame snapshot.

The task uses the current user's limited interactive Windows principal, the
same AC-only/battery-stop and three-minute safeguards as the prelock tasks,
and requests a wake timer. It requires the PC on, logged in and on AC; wake
is not guaranteed. After its trigger, inspect the actual task result and
`receipt.json`, verify both source hashes and back up the raw ignored files.
Compare subject and teammate status changes with the original frozen receipt
**without** changing candidate membership, model probability, recorded ask,
qualification rules or the earlier context strata. Asset publication times
and the local clock proof are source chronology, not per-player update times
or confirmation of game-day participation.

The task action is:

```sh
python -m sportsbet.quant.kalshi_stat_only_context_refresh \
  --context-receipt .local/kalshi-stat-only-teammate-context-pre-result-20261004.json \
  --baseline-dir .local/nfl-injury-source-audit-20261004 \
  --output-dir .local/nfl-context-refresh-20261004
```

### Predeclared refresh comparison

Before the refresh task ran, `kalshi_stat_only_context_change` fixed the
comparison rule for its future source snapshots. It first independently
replays the original 70-candidate/11-high-probability context receipt, the
later receipt, the **raw** GitHub release-response bytes, both exact source
files, all 32 team identities, and the two-host clock chronology. For each
original candidate it compares the subject's report state, same-team roster
state, and the set of same-team QB/RB/FB/WR/TE teammates marked Out or
Doubtful. It reports changed-state counts separately for all 70 and the fixed
11, plus refreshed subject report and roster-state counts. Missing or changed
source identities fail closed. The denominator cannot be reselected after
seeing injuries. The original probability, paper decision, displayed ask and
context stratum remain unchanged. Any source change is **not** an observed
betting edge, a causal adjustment, a game-day active confirmation, or a
qualified consumer pick.

To score after an actual refresh receipt exists, use
`python -m sportsbet.quant.kalshi_stat_only_context_change` with the frozen
`--pair`, `--market`, `--forecast`, `--quotes`, `--decisions`, `--source-dir`,
`--schedule` and `--context-receipt` arguments above, then
`--baseline-dir .local/nfl-injury-source-audit-20261004`,
`--refresh-dir .local/nfl-context-refresh-20261004`, and a new exclusive
`--output` under `.local/`. Inspect the scheduled task and refresh receipt
first. If the task was missed or the source remained unchanged, report that
state; never backfill from a postgame archive.

## Refresh clock proof before source reads

The one-time refresh now replays both independent HTTP Date observations **before** reading either public GitHub release listing. It checks the recorded host/status/cache age, chronology, bounded round trips, recomputed local offsets and inter-host agreement, and requires numeric finite proof fields rather than accepting booleans. The same validator replays the saved proof after capture. This prevents an invalid but self-hashed timing receipt from causing source reads or passing the later context comparison. It does not change the 10:45 UTC task trigger, two source identities, pinned baseline bytes, candidate membership, model probability, paid credit use, or quote schedule.

A focused test altered an otherwise valid timing proof to a boolean round-trip with its record hash recomputed; the pre-read gate refused before the mocked source was requested, and replay rejected the tampered receipt. Adjacent context/clock tests passed 11/11; full backend 2,082 passed/72 skipped with seven existing pandas warnings. The actual task remains unrun until its natural trigger. The change does not assert a game-day injury status or an edge.

## Supplemental exact teammate status comparison before refresh

The original `kalshi_stat_only_context_change` v1 stays frozen and replayable. Its predeclared acute **set** comparison detects a teammate entering or leaving Out/Doubtful, but an Out-to-Doubtful switch for the same teammate leaves that set unchanged. It also does not report Questionable or skill-position changes. These differences are material current-context diagnostics, although they cannot themselves establish a model adjustment or an edge.

The separate `kalshi_stat_only_context_status_detail` v1 was added **before** the scheduled 10:45 UTC refresh and first 13:30 UTC kickoff. It first replays the original v1 comparison and the raw, clock-verified later injury/roster source; then it compares exact same-team QB/RB/FB/WR/TE teammate identities, report statuses and positions, excluding the forecast subject. Aggregate candidate-level counts retain all **70** original paper decisions and the predeclared **11** high-probability decisions; distinct affected clubs are reported separately. An absent injury row means "not listed," not active. It does not recompute target share, probabilities, prices, candidate membership or game-day participation, and does not expose player rows publicly.

After the naturally scheduled refresh receipt exists, run to a new ignored output path:

```powershell
.\.venv\Scripts\python.exe -m sportsbet.quant.kalshi_stat_only_context_status_detail `
  --pair .local/verified-timely-pair-20261003/pair.json `
  --market .local/verified-timely-pair-20261003/market-archive.json `
  --forecast .local/kalshi-stat-only-probabilities-20261004.json `
  --quotes .local/kalshi-stat-only-quotes-20261004.json `
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json `
  --source-dir .local/verified-timely-pair-20261003/sources `
  --schedule .local/team-share-sources/games.parquet `
  --baseline-dir .local/nfl-injury-source-audit-20261004 `
  --refresh-dir .local/nfl-context-refresh-20261004 `
  --context-receipt .local/kalshi-stat-only-teammate-context-pre-result-20261004.json `
  --output .local/nfl-context-status-detail-after-refresh.json
```

Synthetic tests prove that original v1 can report zero change while the supplemental report catches Out-to-Doubtful and Questionable removal; no candidate is reselected. Focused adjacent tests pass **7/7**, full backend **2,084 passed/72 skipped**. A real frozen-input dry run failed on the absent refresh directory and wrote no output. No new source request, paid credit, wager, model or consumer pick was made.

## Actual scheduled refresh and frozen comparison

The one-time local task ran at **2026-10-04 10:45 UTC** and exited successfully.
The raw five-file capture was independently replayed with
`kalshi_stat_only_context_refresh.verify`: its recorded time was
`2026-10-04T10:45:06.121759+00:00`, with receipt record SHA-256
`8fcefe878d34f1918cb1f4f28c4c1d7e7bfb102abbc4b402881d3effd3fc3065`.
Both public assets changed from the frozen baseline and passed raw release
metadata, asset-hash, two-host clock and pregame chronology checks. The new
injury asset SHA-256 is
`ea65b0e040b55dd24777d3a96902a7635a3a262910af6052b60d93ecd0907b5c`;
the weekly-roster asset SHA-256 is
`d67c5a647e294c6272d8feaa3ae91faa33a52a8a0326ad0f2cd8cd8ce4b736c6`.
An independent raw backup under the public workspace's ignored `.local/`
directory has identical SHA-256 hashes for all five files. Raw source bytes
and player-level details remain out of Git.

The predeclared original v1 change audit replayed the same **70** fixed paper
candidates and **11** fixed high-probability candidates. It found zero subject
report, subject roster or acute Out/Doubtful teammate-*set* changes in both
denominators. All 70 subjects remained on the same team roster in this archive;
that is not confirmation of game-day participation. Original audit report
record SHA-256:
`19513dadabce11efb87ed05ff1759d549805fa2b85f8933e71d344b80cbfa7ea`.

The separately predeclared exact-status audit found **two of 70** candidates
with a Questionable skill-teammate status change, across **one** club; it found
**zero of 11** in the fixed high-probability subset. It found no Out/Doubtful
status or skill-position change. This is precisely the status detail that the
original acute-set comparison could miss. Supplemental report record SHA-256:
`9022f089a3ce1a3a4a61e45ded603887126de2a92cf3ca96d06413be454c24f0`.
Neither audit changes candidate membership, market asks, model probabilities,
qualification, the dashboard, or the future result denominator. No price or
outcome was measured by this refresh, so it establishes no edge or 75% rate.
