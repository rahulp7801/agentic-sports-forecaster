# Reusable stat-only NFL paper capture

The October 4 cohort used private one-off scripts. Three tracked modules now
reproduce the original pregame receipts without changing its frozen model or
five-point paper selection rule:

1. `kalshi_stat_only_transfer` replays the captured market/source pair, pinned
   schedule, player history, and the original stat-only artifact offline.
2. `kalshi_stat_only_exact_quote` makes one bounded, unsigned public Kalshi GET
   sequence for the exact forecast tickers before the one-hour board lock. It
   cannot make an authenticated request, an order, or a paid sportsbook request.
3. `kalshi_stat_only_decision` applies the existing five-point gross margin and
   one-per-player-game rule to that one quote receipt offline.

For the retained October 4 v3 pair, offline replay of the transfer produced
the same 144 forecasts and 233 eligible contracts. Replaying all eight retained
public quote response pages at their original timestamps produced a receipt
equal to the original 144-ticker quote receipt. Replaying the paper decision
produced the original 70 candidates over 15 games. These equality checks did
not fetch new prices or use future results. The full backend suite passes.

The source pair builder has since moved to v4 for Jacksonville team aliases.
The transfer supports both v3 and v4 and checks the source-builder replay, but
the v4 path has not yet been validated on a **fresh live** captured pair. An
offline rehearsal rebuilt a v4 pair from the original frozen market and
source bytes at their original pregame times, then ran transfer, exact-quote
receipt construction from retained response pages, decision, strict prior-20
control, and evaluator preflight. It produced 151 model forecasts and 70
paper candidates over 15 games; seven v4-only tickers remained explicitly
missing because the old v3 quote read had not requested them. This is a
workflow test with reused prices, not a second prospective cohort, current
quote collection, or an outcome. The v4 path must fail
closed if its source replay or schedule aliases disagree. The October 4
`kalshi_stat_only_forward_eval` remains hash-pinned to the original v3 cohort;
it **cannot score a later v4 cohort**. The separate
`kalshi_stat_only_next_eval` now replays the pair, market, forecast, exact
quotes, decision, **strict last-20 history control**, schedule and source
manifest, and writes an exclusive pregame commitment with their raw
file hashes. It later refuses changed hashes, early venue results, or a
missing commitment. Its mathematics reuse the frozen model and existing
five-point policy. It labels the broad retained-history comparator accurately
and leaves `edge_established`, ROI, CLV, and qualification unavailable. The
Its later paired probability support requires the model to beat market,
broader retained history and strict last-20 history under the same fixed
game/player interval gates. The commitment hash must be published to the private remote **before the first
selected kickoff**; a timestamp inside a file alone is not independent proof.
An offline replay of the new preflight on the October 4 retained inputs
matched all 452 market contracts, 233 eligible source contracts, 144 model
forecasts, and 70 paper candidates over 15 games. The new generic strict
last-20 control recreated all 144 rows of the separately pregame-committed
original control exactly. It did not inspect outcomes.

A positive-path synthetic settlement test found that the shared interval
routine accepts only its original `market` and `prior20` comparator names.
The next scorer now computes strict last-20 intervals under the existing
`prior20` mathematics and relabels their keys afterward. Two independent
synthetic game clusters exercise that path and a missing quote remains out of
the paired subset. This prevents a future authenticated result from failing
solely on an unsupported comparator label; it is a code-path test, not a
measured win or edge.

The next independent NFL opportunity is the October 8–12 slate, with 15
scheduled games in the current pinned schedule. The one-shot
`kalshi_stat_only_next_capture` orchestrates the same steps inside an
exclusive ignored `.local` directory: stage six hash-checked free nflverse
assets, capture one public Kalshi market archive, pair it with the source
model, replay the stat-only artifact, read exact public asks once, freeze the
paper decision and strict last-20 control, and write the pregame commitment.
The market watcher is also forced through the unsigned venue reader during
this one-shot task; an unexpected future authenticated call fails before
credentials are used.
An existing attempt
directory or a missed capture window aborts before any network read. A failed
attempt remains visible and cannot be retried under the same identifier.
The task makes no paid Odds API, sportsbook, authenticated venue, dashboard
publication, card, order or wager call. A market/source build can still fail
if coverage is incomplete or the five-minute quote age expires; that failure
is part of the attempted denominator.

Two separate pregame attempts are useful because Thursday player markets may
be available before Sunday markets: October 8 at 17:00 UTC and October 10 at
17:00 UTC. The matching one-time limited-user Windows tasks
`SportsbetStatOnlyNext20261008T1700` and
`SportsbetStatOnlyNext20261010T1700` were registered and verified `Ready`
on October 4. Their local 10:00 Pacific triggers map to those UTC times;
each allows a ten-minute start window, a 15-minute execution limit, and
an exclusive output directory. They run only if this PC is on and the user is
logged in. A missed or failed attempt is evidence of missing coverage, not a
reason to backfill a pregame quote after kickoff. When evaluating them, count
each distinct game only once for the independent-game threshold; repeated
games are timing diagnostics. Inspect
their task result and private receipts, independently replay the commitment,
then publish only the commitment hash to the private remote before the first
selected kickoff. The `kalshi_stat_only_remote_anchor` tool writes a small
tracked marker containing that hash. After it is pushed to private PR #345,
preserve that exact commit under
`refs/heads/research/next-nfl-stat-only-<UTC capture stamp>-anchor` on the
same private remote before amending the PR again. This is a ref to the
existing commit, not another commit or another market read. The v2 remote
anchor verifier checks the exact local marker blob, that remote ref's OID,
and GitHub's **server-dated** `HeadRefForcePushedEvent.afterCommit` and
`createdAt` for the PR push. A Git
author or committer date is not accepted as proof because the client controls
those dates. The push must occur after the recorded commitment and before
the first selected kickoff; later branch changes must retain the anchored
commit object. GitHub documents the [pull request force-push timeline
event](https://docs.github.com/en/graphql/reference/pulls) and its commit and
server-created time. Keep complete attempted denominators and failures.
The preservation ref keeps the object available; only GitHub's earlier
server-dated PR push proves
pregame timing. The original October 4 cohort's preserved objects and limits
are recorded in `2026-10-04-stat-only-remote-proof.md`. Venue results must be
authenticated and later matched to the same exact contracts,
asks and pregame receipts. The separate
`kalshi_stat_only_next_settlement_capture` replays the pregame commitment
before any venue request, requires the full-cohort gate and a fresh two-host
clock proof, and reads every original exact contract once through unsigned
public calls. It saves a bounded raw receipt even if aggregate audit fails.
The next evaluator verifies its receipt hash, commitment binding and clock
proof before scoring. Schedule a result read only after the actual selected
cohort's final kickoff plus six hours; its receipt does not exist yet. Until
the commitment is remotely anchored and
enough independent games settle, leave consumer qualification and edge claims
false.

### Pregame injury and roster source receipt

The fresh v4 one-shot capture now observes the free nflverse current-season
injury and weekly-roster release assets after its six model-source files are
staged and before any venue market or exact ask read. It records the bounded
raw release metadata, exact asset bytes, SHA-256 digests, and observed time in
its private `context/` directory. The pregame commitment includes the context
receipt hash. Later commitment preflight replays the metadata, asset bytes,
source chronology and receipt hash before settlement. If a free source is
unavailable, the capture records `status=unavailable` and its error class;
that is missing context, **not** a clean injury report. A failed model-source
week still stops before market collection.

This sidecar is a diagnostic for teammate and participation research. It does
not change the frozen model, five-point paper decision, quote set, comparator,
dashboard qualification or the required independent-game threshold. The
public archive has no update time on each individual injury row, and an
active weekly roster is not proof of game-day participation. Any later
stratification must preserve these limits and the entire original attempted
denominator. The source receipt must be anchored along with the existing
pregame commitment before the first selected kickoff.

### Additional independent weekly attempts, October 4 registration

The October 4 cohort covers only 15 games, and October 8/10 sample the same
following NFL week. To approach the fixed 50-independent-game evaluation gate
without treating repeat captures as new games, four more **one-shot** free
public-source attempts are registered for October 17, 24, 31 and November 7,
each at 17:00 UTC. Their task names are respectively
`SportsbetStatOnlyNext20261017T1700`,
`SportsbetStatOnlyNext20261024T1700`,
`SportsbetStatOnlyNext20261031T1700` and
`SportsbetStatOnlyNext20261107T1700`. Each uses its own matching
`.local/next-nfl-stat-only-<UTC date>` exclusive directory and the same pinned
schedule, unsigned reader, ten-minute window, 15-minute execution limit,
interactive limited principal, and AC-only setting as the October 10 task.
The November 7 trigger is 09:00 Pacific standard time; the other three are
10:00 Pacific daylight time. The Windows task scheduler reported all four
`Ready` with matching next run times and an existing Python executable.

These dates sample distinct future NFL weeks. The pinned schedule has 14, 14,
14 and 15 regular-season games in those weeks; Saturday capture follows each
Thursday game, so these are **potential** independent games, not promised
forecasts, quote coverage, paper decisions or results. A source-week failure,
missed task, unavailable public market, missing price or delayed remote anchor
stays a recorded failure; do not silently retry after the ten-minute window.
Inspect each output, verify and privately anchor its commitment before its
first selected kickoff, then wait for authenticated exact-contract settlement.
No task uses the paid Odds API, a card, order placement or a wager.

### Durable local capture checkout

The six future one-shot tasks originally pointed into a Windows Temp checkout.
On October 4, an independent clone of the exact private PR head was created
at the outer project's ignored `.local/private-release-20261004/` directory.
The installed Python environment and pinned schedule were copied there; the
schedule SHA-256 is
`4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662`.
The clone has its own Git objects and private GitHub remote, and the outer
checkout ignores its entire directory. Its capture module imported from the
copied environment and 11 focused no-network capture/source-week tests passed.

Only the task actions for October 8, 10, 17, 24, 31 and November 7 were
repointed to that durable checkout. Read-only verification afterward confirmed
all six `Ready` states, exact 17:00 UTC triggers (including the November
daylight-saving change), distinct exclusive output paths, 15-minute task
limits, AC requirement and limited interactive principal. None was run as
part of the move; the original Temp checkout remains available for the
separately frozen October 4 evaluation. The task still requires the computer
to be on with that user logged in at capture time.

On October 4, a read-only check found all six future tasks still `Ready`,
with valid executables and working directories, but with wake disabled and
starting/staying on battery prohibited. Their definitions were backed up in
ignored `.local/task-backups-20261004/`. Only the Windows power settings were
changed: wake requested, battery start allowed, and battery operation allowed
to continue. Exported before/after task definitions confirm identical
commands, UTC-mapped triggers, limited interactive principal and 15-minute
execution limit for each task. This improves the chance of a natural one-shot
capture; it does not guarantee a wake or run without a logged-in session.
The capture still enforces its ten-minute time window and exclusive attempt
directory before any free source or market request. No task was manually run
and no API request, purchase, order or bet occurred during this check.

## Latest completed week coverage before a new market read

The source manifest previously required each public asset to predate capture
and have its declared hash, but that did not prove the current-season stat and
snap files covered the whole latest completed week. A file updated after one
Thursday game can have a new timestamp and a new maximum week while most
teams are still missing. That would make the next paper model appear current
while its teammate and player histories lagged for most of the slate.

The October 8/10 one-shot path now derives the latest **whole** regular-season
week whose scheduled games all ended at least two calendar days before capture.
The chosen week's last scheduled game must also be no more than seven calendar
days old, so an incomplete newer schedule cannot quietly fall back to a stale
older week.
It requires the current-season player stats **and** snap assets to contain
exactly that week's scheduled team set. The check runs after the six source
assets are staged and before any market watcher or exact quote call. A stale
archive leaves the exclusive attempted capture as failed; it cannot be retried
or backfilled as a pregame observation. The postcapture commitment preflight
recomputes the same check from hash-pinned source and schedule bytes, so later
result scoring cannot silently accept an incomplete weekly source.

On the retained October 3 source files, an October 4 16:00 UTC offline check
passed **week 3, 16 games, 32/32 teams** in both stats and snaps. At a
simulated October 8 17:00 UTC capture time, those identical files correctly
failed because week 4 would be the latest completed week and the archive then
contained only two week-4 teams. This is a freshness failure demonstration,
not a prediction or result. The actual October 8/10 one-shot tasks must stage
new free sources and pass naturally; no extra asset or sportsbook quote read
was made for this check. A full-team weekly archive still cannot confirm final
game-day active status, a specific player's participation, or a betting edge.

## Multiple independent slates

The separate `kalshi_stat_only_next_series` scorer accepts only fully
commitment-replayed v4 cohorts with the same frozen stat-only model artifact
and implementation. Its private manifest cannot refer to paths outside its
own evidence directory. It authenticates each cohort's venue receipt first. If
two captures contain the same scheduled fixture, the **earliest privately
anchored pregame cohort owns the entire game**, ordered by GitHub's server
push time and then commitment hash. An offline library call without remote
verification uses recorded local capture time only for a conditional
diagnostic. Its missing quote, missing forecast, or unverified outcome
cannot be replaced by a later, more favorable observation. The report counts
attempted games, overlapping games excluded, unique selected games, paired
contracts and paired games separately. On the fixed paired subset it computes
model-minus-market, model-minus-broad-history, and model-minus-strict-last-20
game/player cluster intervals. At least 50 independently paired games and
complete selected forecast/quote/result coverage are required even for a
conditional paired-skill signal. It also reports the original candidate
denominator, verified wins and whole-game win-rate interval when complete.

No later cohort has settled. The series CLI queries the live private GitHub
timeline for **every** commitment marker and refuses a missing, changed, or
late push. Without that verification, its library API retains
`remote_pregame_anchor_verified=false` and `probability_support=false`.
`paired_skill_signal` is a conditional statistical diagnostic; it
cannot qualify a consumer pick or establish executable edge, fees, fills,
ROI or closing-line value. The first-overlap policy is fixed before the
October 8/10 captures and was tested with an earlier missing quote that a
later priced copy was forbidden to replace.

The same first-owned-game policy now also retains a separate, fixed
**model-probability at least 75%** subset of the original paper candidates.
It records its attempted contracts and independent games, venue result states,
verified-subset wins, and a full-group win rate and whole-game bootstrap
interval only when every selected result authenticates. A descriptive
`descriptive_75pct_threshold_met` flag stays false unless the *entire* cohort
is complete, every commitment is verified on the private remote, this subset
spans at least 50 independent games, and the lower ends of both the
contract-weighted and equal-game 95% intervals exceed 75%. Duplicate later
game captures cannot replace an earlier missing candidate. This rule measures
the advertised individual-pick target without changing the frozen model,
asks, paper policy, qualification, or primary paired-skill gate. It remains a
descriptive prospective diagnostic, not a guarantee of future accuracy or a
fee-adjusted executable edge. No future cohort result has been observed.
