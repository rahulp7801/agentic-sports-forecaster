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
the tool checks the exact commit blob and GitHub's **server-dated**
`HeadRefForcePushedEvent.afterCommit` and `createdAt` for that commit. A Git
author or committer date is not accepted as proof because the client controls
those dates. The push must occur after the recorded commitment and before
the first selected kickoff; later branch changes must retain the anchored
commit object. GitHub documents the [pull request force-push timeline
event](https://docs.github.com/en/graphql/reference/pulls) and its commit and
server-created time. Keep complete attempted denominators and failures. Venue
results must be authenticated and later matched to the same exact contracts,
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
