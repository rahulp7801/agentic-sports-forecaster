# Frozen free-market NFL comparator

The private natural public collection artifact from run `37049246268` was
downloaded without requesting any new quote. Its lossless artifact manifest
verified all nine files. The NFL market archive's evidence SHA-256 is
`6d999bd7a04185f2483547f0043bdd65694c0e59083c347d81212a2bda1f3e62`;
its internal capture and summary hashes agree. It was captured at
2026-10-02 18:43:24 UTC with 16 game contexts, complete discovery for four
NFL prop series, and 3,189 structured quote lines.

`kalshi_market_cohort` v1 freezes one deterministic, two-sided displayed line
per exact game/player/stat: choose the line whose displayed midpoint is nearest
50%, then the narrower spread, then the lexical ticker. The market midpoint is
computed from the YES ask and the complement of the NO ask. Source hash,
target/team/game identity, pregame request/receipt timing, line, positive size,
and complete discovery are checked. The tool neither queries a provider nor
changes model selection, qualification, quota, reserve, or dashboard output.

The decision time is **2026-10-03 07:29:15 UTC**, before every selected game.
The ignored private receipt is `.local/kalshi-market-cohort-20261003-final-v3.json`.
Its selected-row SHA-256 is
`54bc894dcaa7eca080437d17fa9d4ee90aab951a3f27a20738dd2780e417e8de`.
It commits 417 contracts across 212 quoted player targets and 15 distinct
upcoming games, with first kickoff 2026-10-04 13:30 UTC and last kickoff
2026-10-06 00:15 UTC. Counts are 30 passing yards, 86 rushing yards, 162
receiving yards, and 139 receptions. Another 145 lines were one-sided or
unquoted. No already-finished game was included. The artifact's seven-day
retention makes prompt follow-up necessary; the local copy is ignored and
private. This cohort is a market comparator, **not** model picks or a measured
alpha claim.

An earlier hash-valid public archive from run `36797990857`, captured
2026-10-01 00:48:55 UTC, contains the same Jaylen Warren 3.5 receptions
contract at a 55-cent NO ask, observed 00:48:48 UTC. The accepted sportsbook
forecast was recorded approximately 01:27:52 UTC, about 39 minutes later.
The later 2026-10-01 14:45 UTC archive has a 51-cent NO ask, after the pick.
Neither capture establishes a matching simultaneous price at the pick's
decision time. The Warren outcome is one production result from one game;
selection after seeing that result would be hindsight. This finished game is
excluded from the frozen comparator.

One read-only [official Kalshi exact-market response](https://external-api.kalshi.com/trade-api/v2/markets?tickers=KXNFLREC-26OCT01PITCLE-PITJWARREN30-4&status=settled&limit=20)
on October 3 returned that Warren contract as `finalized`, `result=no`,
with YES settlement value 0 and settlement time 2026-10-02 04:11:54 UTC.
Its structured player and team IDs exactly match the earlier pregame quote.
The exact line, strike type, and settlement-rule hash also match the capture.
This verifies the venue's outcome for that one contract; it does not repair
the unmatched pick-time quote, prove a 417-contract result, or establish ROI.

To reproduce the cohort from the retained raw NFL JSON archive:

```text
python -m sportsbet.quant.kalshi_market_cohort \
  --market-archive PRIVATE_NFL_MARKET_ARCHIVE.json \
  --frozen-at 2026-10-03T07:29:15Z \
  --output .local/kalshi-market-cohort-replay.json
```

Before scoring, obtain authenticated exact-contract Kalshi settlement and
participant/stat provenance for each selected contract. Do not treat a missing
game log, an inactive player, a no-snap rule, or a stat correction as a loss or
zero. Report unavailable contracts and distinct games. Compare separately
against model forecasts only when model receipt, player/game/line identity,
source availability, and quote time all meet the frozen same-time rules. This
market-only cohort cannot establish a 75% win rate, positive ROI, execution,
or a consumer recommendation. Recheck after the 2026-10-04 games and before
the source artifact expires.

The separate `kalshi_market_settlement` v1 path uses the same frozen cohort
and raw market archive. Its read-only collector refuses to run until six hours
after the last selected kickoff, then requests only the precommitted 417
tickers in batches of at most 20 via public Kalshi GETs. It uses no API key,
paid sportsbook feed, order endpoint, database write, or dashboard publication.
The archive is exclusive and private; a provider error remains an explicit
unavailable batch. Run collection no earlier than 2026-10-06 06:15 UTC:

```text
python -m sportsbet.quant.kalshi_market_settlement \
  --market-archive PRIVATE_NFL_MARKET_ARCHIVE.json \
  --cohort .local/kalshi-market-cohort-20261003-final-v3.json \
  --output .local/kalshi-cohort-settlements.json
python -m sportsbet.quant.kalshi_market_settlement \
  --market-archive PRIVATE_NFL_MARKET_ARCHIVE.json \
  --cohort .local/kalshi-market-cohort-20261003-final-v3.json \
  --settlements .local/kalshi-cohort-settlements.json \
  --output .local/kalshi-cohort-settlement-audit.json
```

The offline audit replays and compares the full frozen selection, validates
the settlement archive hash, exact ticker/player/team/line/rules, binary
whole-dollar result, and postgame settlement clock. Every selected contract
is counted as venue-verified, unavailable, missing, nonfinal, nonbinary, or
invalid. Brier scores use only venue-verified contracts and are labeled as
such; a partial subset is not presented as full-cohort performance. Distinct
verified games and an equal-game score expose correlated lines. No sportsbook
model is paired here, and ROI, CLV, alpha, and execution remain unclaimed.

## Frozen NFL current-role shadow

A separate private, outcome-blind forecast was frozen at **2026-10-03
08:31:42 UTC**, before the first selected kickoff. It uses the predeclared
20-game current-role prior strength, with at least two 2026 games for the
quoted team, a unique GSIS/PFR crosswalk, and positive offensive snaps for
every counted game. A missing stat row becomes zero only when offensive snaps
prove participation. Other recorded offensive production without a matching
snap receipt makes that player's prop unavailable. The two latest played games
must match the quoted team. Recent target, carry, or attempt shares and the
largest teammate share are recorded as context; they do not change the
forecast. Current roster and availability are not independently verified.

The six official nflverse parquet assets were all updated **before** the
2026-10-02 18:43:24 UTC market capture. The pinned `stats_player` asset IDs
are 513240737, 513243463, and 605933905 (2024–26); the pinned `snap_counts`
IDs are 301000083, 585953424, and 605418286. Their exact SHA-256 values and
update times are in `kalshi_role_shadow.SOURCES` and are checked on replay.
The prequote crosswalk SHA-256 is
`8fa1995e608405945c2f1a6289a3ac718f35c9b5845344b0c0d4334d480b8750`.
These are free existing sources; this step made no paid odds request.

The ignored private receipt is `.local/kalshi-role-shadow-20261003-final-v3.json`,
SHA-256 `119331ba1764ee74f309384823c89035c81ac78ef7a5b0911156f6ccb760d627`.
Its implementation hash is
`c360a69d0d77d6f39e953bf1b657b28f05b1a0be51e1555ecebd0259c8b4f8f5`
after normalizing CRLF to LF for Windows/Linux replay;
its 289 forecast rows hash to
`d82504dcdd27a0ac573b957db7e9d1f52994fa2403d1dcdbd3c2a043a4e4c9b2`.
Coverage is **289/417 contracts, 146 players, 15 games**: 20 passing yards,
54 rushing yards, 116 receiving yards, and 99 receptions. The other 128 are
explicitly unavailable: 90 have fewer than 20 offensive games, 20 lack
sufficient recent quoted-team role, and 18 lack a unique identity. This
is a research shadow, with zero qualified picks and no established edge.

The frozen market quote preceded model generation by **49,705–49,706
seconds** across the 289 forecast pairs (about 13 hours 48 minutes), so
**0/289** meet the five-minute model/quote pairing window. Their probability
difference is a research hypothesis rather than an executable same-time price
edge. `kalshi_role_shadow_eval` replays the full
source and forecast receipts, then scores only the same exact contracts with
venue-verified YES/NO outcomes. It reports paired model and market Brier and
log loss, equal-game differences, quote/model age and five-minute pair counts,
missing result states, and full denominators; it never
labels this result as ROI, CLV, or a consumer pick. The current cohort has
only 15 games, so it cannot alone satisfy the previously frozen NFL role
protocol's 50 independent-game evidence gate even if every contract settles.
That protocol also requires favorable game- and player-clustered upper 95%
confidence bounds for both scores against production and market baselines;
this offline Kalshi comparison alone does not provide those tests. Further
prospectively frozen cohorts and contemporaneous executable price captures
are needed for an edge claim.

For a **future existing natural archive**, `kalshi_pair_capture` can freeze a
new market cohort and role shadow in one private receipt. It requires every
selected quote to be at most five minutes old at model completion, limits
the model build to 30 seconds, checks prequote source hashes and earliest game
start, and writes exclusively to an ignored file. It makes no provider
request. If artifact delivery exceeds the window, it fails closed; the
archived quote must not be relabeled as current. Its nested `cohort` and
`shadow` can later be passed to `kalshi_role_shadow_eval --pair` after exact
venue settlements. The displayed midpoint still lacks executable depth and
the model still lacks current-roster proof, so a timely pair remains research
evidence rather than a qualified consumer pick.

```text
python -m sportsbet.quant.kalshi_pair_capture \
  --market-archive FRESH_PRIVATE_NFL_MARKET_ARCHIVE.json \
  --source-dir PRIVATE_HASH_PINNED_NFL_PARQUETS \
  --source-manifest PRIVATE_HASH_PINNED_NFL_PARQUETS/source-manifest.json \
  --output .local/kalshi-fresh-pair.json
```

The real October 2 archive was rejected by this command on October 3 with
`Market quotes are not fresh at pair capture`; it wrote no pair. The next
operational step was to place the offline pairing immediately after free
collection in the existing worker. The October 2 public-daily market was
captured at 18:43:24 UTC, but the worker finished at approximately 18:48 UTC
and its public artifact was packaged at approximately 18:49 UTC. Downloading
that artifact and then building a model would systematically exceed the frozen
five-minute quote window.

The proposed private workflow stages six bounded official nflverse source
assets and the raw release metadata before its natural `public_daily` market
collection. The 2026 player-stat asset was updated again at **2026-10-03
09:04:21 UTC**, after the original October 2 quote. The v1 source set and
receipt above remain frozen; a forward-only v2 source manifest pins the
current release IDs, update times, URLs, sizes, and SHA-256 values per run.
The actual six current assets were staged and replay-loaded locally on
October 3 without an odds request. The v2 builder uses the unchanged v1
forecast algorithm. It refuses a manifest or asset that postdates the new
market capture.

For an NFL `public_daily` run, the worker now attempts the private pair as soon
as the existing free `market_watch` call returns its raw archive. It does not
trigger another quote call and has no effect on the public market snapshot or
consumer picks when research fails. The receipt requires a model build within
30 seconds, all selected quotes at most five minutes old at completion, and
at least one source-backed forecast. A successful pair, its raw market
archive, exact six parquet inputs, source-release metadata, and pinned identity
crosswalk are replay-checked, scanned for secrets, and packaged in a private
seven-day GitHub artifact. The repository artifact budget remains 350 MB with
room reserved for the same run's public evidence; the account Actions budget
remains the user's $0 stop-usage setting. No card, paid provider request,
order, or bet is involved. A storage-gate rejection leaves the run without a
retained private pair and must not be interpreted as a negative model result.

The same pregame pair now contains a fixed **research** decision receipt. For
each source-backed forecast it compares the model probability of YES with the
captured YES ask, and the complement with the captured NO ask. It selects the
larger gross gap only when it is at least **five percentage points**; otherwise
it abstains. The 5-point margin is predeclared for prospective measurement,
not fitted or validated as a profitable threshold. Both asks must show
positive size. The receipt commits the exact contract, side, displayed ask,
size, game, model probability, selection hash, and the full forecast/abstention
denominator before any result. Later `kalshi_ask_policy` replays the original
model and exact venue settlement, then reports verified and unavailable
candidate results and gross unit profit on the verified subset. The decision
timestamp is recorded after the rule runs and must still be within 30 seconds
of model start, five minutes of the oldest selected quote, and before the
first selected kickoff. Displayed asks are historical observations: fills,
fees, liquidity at execution, current
roster status, and net ROI remain unverified. It never promotes these rows to
consumer picks or an edge claim.

This workflow is on a private review branch, **not production**. Deployment
depends on the protected private PR's required checks. A timely pair remains
research evidence because displayed midpoints are not executable fills,
current roster availability is not independently verified, and no prospective
game-clustered advantage has been measured. Do not present it as a consumer
recommendation or a 75% win-rate claim.

After 2026-10-06 06:15 UTC, use the bounded read-only settlement collector
above, then run the offline paired audit with `--market-archive`, `--cohort`,
`--shadow .local/kalshi-role-shadow-20261003-final-v3.json`,
`--source-dir .local/kalshi-source-20261003`, `--settlements`, and `--output`.
Preserve the raw market archive, cohort, six parquet files, crosswalk and
shadow receipt privately; the GitHub collection artifact expires in about a
week. Do not re-freeze this cohort after outcomes are known.

For a later *v2 timely pair* that contains the pregame ask-policy receipt, run
the separate displayed-ask outcome audit against the same authenticated exact
venue archive. The October 2 stale pair cannot use this protocol.

```text
python -m sportsbet.quant.kalshi_ask_policy \
  --pair PRIVATE_TIMELY_PAIR.json \
  --market-archive MATCHING_RAW_MARKET_ARCHIVE.json \
  --source-dir MATCHING_PREQUOTE_SOURCE_DIR \
  --settlements MATCHING_EXACT_VENUE_SETTLEMENTS.json \
  --output .local/kalshi-displayed-ask-audit.json
```
