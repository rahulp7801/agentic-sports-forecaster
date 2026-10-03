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

The separate `kalshi_market_settlement` v2 path uses the same frozen cohort
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

The original cohort committed the raw market-selection Python file hash.
The settlement reader now accepts only the exact LF or CRLF encoding of that
same source file while still replaying every other frozen field. This was
verified against the retained 417-contract receipt on Windows; no selection,
model, or result receipt was rewritten.

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
October 3 without an odds request. Forward current-role shadow v3 leaves the
v1 role probability formula unchanged and also freezes an independent,
unfitted prior-20 Jeffreys Over probability for every covered contract. This
plain-history comparator was chosen before future outcomes after the
[retrospective quoted-universe diagnostic](2026-10-03-nfl-role-retrospective.md)
found the role formula worse on three 2025 synthetic markets. Neither
probability is promoted to consumer picks. The builder refuses a manifest or
asset that postdates the new market capture.

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
it abstains. Version 2 then retains at most one candidate per player and game:
the largest gross margin, with ticker as the fixed tie-break. It records the
number excluded by this cap so correlated prop types cannot inflate an
individual-decision count. The 5-point margin is predeclared for prospective
measurement, not fitted or validated as a profitable threshold. Both asks must show
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

For forward source receipts, paired evaluator v4 additionally reports the
model-minus-market Brier and log-loss difference with equal weight per game,
then per player/game, then per contract. It uses 10,000 deterministic
whole-game and whole-player percentile resamples for separate 95% intervals;
one game or one player yields no interval for that grouping. Negative values
favor the model's probability forecast. These are descriptive comparisons
against captured market midpoints on venue-verified outcomes. The same
weighted comparison is reported against the frozen prior-20 comparator on
those exact outcomes. They do not
substitute for the frozen production-baseline comparison, 50 independent
paired games, executable asks, fees, fills, or an authenticated return bound.
The October 2 stale-price cohort remains tied to the v1 evaluator protocol
and is not relabelled as v3 evidence.

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

### Predeclared prior-20 ask challenger

A future natural, timely NFL pair now freezes a **second** displayed-ask
research receipt using the already frozen plain prior-20 Jeffreys probability.
This is motivated by the separate exploratory 2025 synthetic-line check in which
the current-role formula scored worse on receiving, receptions and rushing.
That inspected history is development evidence only; neither policy has a
verified prospective edge.

The challenger uses the exact same frozen contracts, two-sided displayed asks,
positive displayed size, 5-percentage-point minimum model-minus-ask gap,
and greatest gap per player/game with ticker tie-break as the role policy.
It reads the decision clock after selecting candidates and requires completion
within 30 seconds of model start, five minutes of the oldest selected quote,
and before the first kickoff. Its independent `prior20_ask_policy` receipt is
recomputed during private artifact packaging and outcome audit. No extra
market request, sportsbook API credit, bet, or consumer-model change occurs.

After a later authenticated venue settlement, score both precommitted policies
on the same source/market pair. Keep every unavailable result in its original
candidate denominator. Report their overlap and different selected exposures;
do not treat two searched hypotheses as independent proof or promote either
from one slate. The optional paired comparison reports role-only, prior-only
and shared player/game exposures. It scores a prior-minus-role gross difference only
where **both** chosen contracts have authenticated venue results, with a
whole-game interval when at least two games are verified. Other outcomes
stay unavailable; that shared subset does not represent either full policy.
The interval is descriptive and unadjusted for two researched hypotheses.
Both outputs are zero-fee, unfilled counterfactuals with null ROI/CLV and `edge_established=false`. Actual fees, executable depth, fills,
roster state and enough independent games remain missing.

```text
python -m sportsbet.quant.kalshi_prior20_ask_policy \
  --pair PRIVATE_TIMELY_PAIR_WITH_BOTH_POLICY_RECEIPTS.json \
  --market-archive MATCHING_RAW_MARKET_ARCHIVE.json \
  --source-dir MATCHING_PREQUOTE_SOURCE_DIR \
  --settlements MATCHING_EXACT_VENUE_SETTLEMENTS.json \
  --compare-role \
  --output .local/kalshi-prior20-displayed-ask-audit.json
```

### Private pair capture visibility

The NFL `public_daily` worker's aggregate market report now includes
`research_pair_status`: `captured_local`, `market_reused`,
`archive_unavailable`, `not_configured`, `source_unavailable`,
`capture_failed`, or `market_unavailable`. It contains no player-level
forecast, candidate, provider credential, file path, or exception message.
`captured_local` means only that the private receipt was saved on that worker;
the later secret scan, replay packaging, storage gate, and artifact upload
must still succeed before it is retained. Other statuses leave the public
market snapshot and its existing success/degraded state intact. Inspect the
scheduled run's final worker report and upload step together before claiming
a timely prospective pair was captured. This status does not make an
observation executable, qualified, profitable, or suitable for promotion.

On the retained October 2 417-contract input, the unchanged v1 model built
289 forecasts in about one second in an offline Windows replay and exactly
matched the frozen forecast hash. This local timing check supports feasibility
of the 30-second model-build window; it does not validate the forward v3
source manifest, guarantee GitHub runner timing, or turn stale quotes into a
timely pair.

### October 3 settlement preflight

A local replay of the unchanged October 2 archive and frozen cohort verified
**417 distinct contract tickers across 15 games**. The bounded reader will
request at most **21** batches of 20 exact tickers, and the last scheduled
start plus its fixed six-hour wait is **2026-10-06 06:15 UTC**. No venue
result was queried in this preflight. A mock-transport regression now checks
the public `GET /markets` request, exact comma-separated ticker filter,
`status=settled`, `limit=1000`, no authentication header, and rejection of
empty, duplicate or invalid tickers. These query parameters match Kalshi's
[Get Markets documentation](https://docs.kalshi.com/api-reference/market/get-markets).
The real response, result identity and unavailable-contract denominator still
require postgame verification; no outcome or edge is inferred now.

### First genuinely timely NFL pair: October 3, before outcomes

This is a separate forward cohort from the October 2 stale-price comparator
above. At 2026-10-03 13:02 UTC, the last natural public capture was 12:28 UTC
and no newer workflow was queued or running. One local `provider='kalshi'`
public NFL-only capture was made at 13:03:52.525290 UTC. The Odds API key was
blank; sportsbook and PrizePicks collectors and signed Kalshi requests were
explicitly forbidden in that process. It made no paid request, purchase, bet,
database write, or dashboard publication. The six source files and manifest
had been staged at 09:14:06.503788 UTC, before those quotes. The fixed forward
v3 model began at 13:03:52.826410 UTC, and the oldest selected quote was
9.293144 seconds old at completion. Private artifact packing replayed the
market, source, model, and both frozen ask-policy receipts.

The private zip is in the original workspace's ignored
`.local/kalshi-prospective-20261003/timely-pair-20261003T130352Z.zip`,
SHA-256 `a66bd1f486d344001bed3e5a2b95014ff31efec83e87ef02eaf26f7396721f73`.
The corresponding pair JSON SHA-256 is
`8df6075f9794837f9c99772cf70d5dbdfb7954a07421ebfda0345494637e9acb`.
The raw player-level rows and source files stay in ignored private storage;
this tracked note contains aggregates only. Do not rewrite or refreeze either
receipt after outcomes arrive.

| Frozen denominator | Current-role rule | Prior-20 rule |
|---|---:|---:|
| Exact two-sided selected contracts | 452 | 452 |
| Source-backed forecasts | 308 | 308 |
| Forecasts unavailable | 144 | 144 |
| Above the fixed 5-point gross ask gap before player/game cap | 217 | 216 |
| Correlated same-player/game exclusions | 91 | 90 |
| Hypothetical displayed-ask candidates | 126 | 126 |
| Distinct games containing candidates | 15 | 15 |

Selected prop types are 30 passing yards, 171 receiving yards, 165 receptions,
and 86 rushing yards. Forecast exclusions are 98 with fewer than 20 verified
offensive games, 27 without sufficient current-team role, and 19 with missing
or ambiguous identity. The two policy candidate sets share all 126 player/game
exposures and choose the same exact contract and side for 125 of them. Across
all 308 forecasts, the mean absolute role-minus-prior probability difference
is only 0.00314. This one cohort offers little selection contrast between the
two researched formulas.

The source files include only the first Week 4 game (two teams) as of this
capture. Thus 293 forecasts have three completed 2026 current-team games,
15 have two, and all 308 carry descriptive teammate usage context. **None has
an independently verified current roster or participation status.** Every
candidate's captured rule has an active-no-snap fair-market-price clause.
These gaps prohibit calling a candidate an executable pick even if its model
probability exceeds a displayed ask. The role and teammate features have no
validated incremental predictive benefit on the retained retrospective tests.

The raw capture includes exact prequote prop fee contexts for all 60 linked
events, with no fee lookup failure. Before outcomes, an offline diagnostic
matched every candidate to its exact quote, event and series fee context.
All 126 displayed at least one contract; none had a recorded active fee
waiver. With the existing one-contract taker fee model and direct balance
precision, all 126 have a modeled cost; the mean modeled exchange fee is
$0.01709444. The frozen model implies positive fee-adjusted margins on all
126 and at least five points on 120, but **these are model expectations, not
observed returns or a measured edge**. The mean model-implied direct net
margin of 0.16339 is a calibration hypothesis in tension with the older
negative exact-price audit. It excludes unobserved fills, slippage, broker
fees, changing depth, and nonbinary participation settlement. Kalshi's
[fee help](https://help.kalshi.com/en/articles/13823805-fees) notes that fees
can vary by market; this diagnostic uses the capture's exact event metadata.
The ignored private diagnostic script SHA-256 is
`a776bfc627f2ffc33851e42e2955ea20583e8f008eba1a975c4ab6a4779765a9f`;
its aggregate report SHA-256 is
`79947efe376a6d2ce48acf79f7a03cd31c1385b68b277efdbff87859b8a1aa7f`.

Under the strictly hypothetical assumption of one fill at each captured ask
and a binary one-dollar settlement for every candidate, the direct modeled
cost across 126 decisions is $65.5939 ($65.96 with non-direct balance
precision). **At least 66 wins** would be needed for positive aggregate
unit payoff under either modeled cost. This is a pre-outcome scoreboard,
not a 75% prediction, ROI, or product promotion criterion. The 126 decisions
come from only 15 games and are correlated. Preserve missing and nonbinary
outcomes in the full denominator and use game-clustered evaluation; do not
infer alpha from a single slate.

The earliest exact venue result query is **2026-10-06 06:15 UTC**, six hours
after the latest scheduled kickoff. The unchanged bounded reader can request
452 frozen tickers in at most 23 public GET batches of 20, with no auth header.
Verify contract identity, rules, player/team IDs, result, and settlement
clock before comparing paired model and market Brier/log loss or hypothetical
fee-inclusive unit payoff. The production in-worker private pair remains
unreleased while the protected private PR is blocked by unavailable CodeQL
checks; the local research success does not establish production retention.

### Prior-day exact-ID availability audit, frozen before outcomes

The retained October 2 public evidence archive (run 37049246268) predates the
October 3 local quote and contains six NFL game availability snapshots. Its
private tar SHA-256 is
`c8700b00f6875f6800ac4ea0882d14fc082a8f7b724490d45c40fbf5eb86510f`.
All six league injury response receipts, the six pairs of roster receipts, and
the pinned nflverse GSIS-to-ESPN crosswalk passed source-hash and prequote-clock
checks. The latest verified league injury receipt was captured at
2026-10-02 18:48:17.528155 UTC. It is a prior-day report, not a final lineup.

For the **same frozen 126 current-role ask candidates**, exact ESPN athlete-ID
and quoted-team matching found 110 `Active` injury-report labels, 8
`Questionable`, and 8 absent from the report. These are injury-feed labels;
`Active` is not a verified game-day active designation, and absence from the
report is not proof of availability. Only 12 teams across six retained games
had archived rosters: 45 candidates matched a roster athlete by exact ID and
team; 81 had no retained team roster to check. All 45 roster matches had a
prior-day roster status of `Active`, while two of those 45 also carried a
`Questionable` injury report. This demonstrates why the two source fields must
remain separate. It does not revise the frozen model, selection rule, or zero
qualified-pick count.

Both private overlays reproduce byte-for-byte from the frozen pair and source
tar. The injury overlay JSON SHA-256 is
`b38c6ef45123e481b25982180b429a7ebd21ef6ce9bda03814d8c19d8acdfcb8`;
its replay script SHA-256 is
`974777e61239142acca0802cd74e02e88e93175db363577820229172b23fdbe9`.
The exact-ID roster overlay JSON SHA-256 is
`1ba27b9ceca0fa57d6dd3dd2d68ad9edf505f45c8d6d0e8ea448654bb7ae2c80`;
its replay script SHA-256 is
`235f2ce0b18afff0180a42e5e0bbe9d9e5a9e2ac772dd56bbc1831434cf1bca1`.
All four files are in the original workspace's ignored
`.local/kalshi-prospective-20261003/` directory; player-level rows stay private.
Later availability evidence must be recorded with its own retrieval time and
cannot be inserted into the prequote model input or used to reselect this cohort.

### Saturday pregame injury-label movement, separate from the quote freeze

At 2026-10-03 13:45:43.401316 UTC, one bounded, unauthenticated public
ESPN league injury read was captured privately, after the 13:03 quote and
before every selected game. It used no Odds API credit, card, order, or
additional quote request. The provider timestamp was 13:45:35 UTC. The raw
response SHA-256 is
d60966479f488195e1cc1050b2303285da7ab12f8ad724249fd49b6452681b27;
the saved source receipt SHA-256 is
078e9440b989282c6383e4338e6032fee8f34018dbded2d36af71f07877bb63d.
The exact-ID overlay replays byte-for-byte, SHA-256
f5e8ccf8af4026af6441feb37fe68fec2a7419195d560a02697b5f14ad30f308;
its script SHA-256 is
df4e57ce24db74d8393c1e1a9cbeb128f3a6bbcd68f61d388ff70e0a20c1ef11.

The unchanged 126-candidate denominator now has 112 Active injury-feed
labels, 5 Questionable, and 9 not reported. Against the retained prior-day
source, the transition counts are: 108 Active-to-Active, 1
Active-to-Questionable, 1 Active-to-not-reported, 4
Questionable-to-Active, 4 Questionable-to-Questionable, and 8
not-reported-to-not-reported. Thus six labels changed within about 19 hours.
A feed label is not a final game-day roster or participation guarantee.
This later source is descriptive context only: it cannot be backdated into the
earlier quote/model freeze, alter any of the 126 selections, or create
qualified consumer picks. Preserve the full denominator when venue results
arrive.

### Exact prop-event settlement binding and fee-inclusive frozen scorecard

Before any October 4-5 games settled, an offline audit found that NFL prop
contract tickers include a player segment between the event ticker and the
line. Removing only the last ticker segment therefore produces the wrong
event identity. The prior exact-result verifier would have classified
authentic prop settlements as invalid. The verifier now reads the explicit
event ticker from the hash-verified pregame quote, checks its series and
contract prefix, and matches the returned settled market to that event.
No frozen contract, model version, candidate, quote, or outcome was changed.
Offline preflight verified explicit event identity for all 417 contracts in
the October 2 cohort and all 452 in the October 3 timely cohort, each across
15 games. Synthetic wrong-event results still remain unavailable, never wins
or losses. The complete Kalshi-focused suite passed 136 tests.

A separate versioned fee-inclusive unit shadow was frozen before outcomes.
It replays the original displayed-ask policy and the exact quote/event/series
fee context for each candidate. With one hypothetical taker contract per
candidate, the October 3 role and prior-20 rules each cover all 126 candidates
and 15 games. Both have an aggregate modeled direct cost of $65.5939 and
non-direct cost of $65.96; under a strictly binary one-dollar payout,
at least 66 winning settlements would be needed for positive total unit
payoff. Their individual candidate-cost row hashes differ because one of
126 shared player/game exposures uses a different contract and side. The
new scorer never alters the precommitted policies or implies actual fills.
After exact venue collection, it independently replays model/source and
settlement evidence, retains nonbinary or missing contracts in the full
denominator, and reports only a labeled hypothetical unit payoff on verified
binary results. It also reports an equal-game mean and deterministic
10,000-resample whole-game 95% interval for that verified subset; missing
results never become losses. Actual ROI and CLV remain null;
edge_established stays false.

The matching October 3 raw market archive extracted from the existing private
zip has SHA-256
05b2c78304cb80c7923bf530e1b2a8a9b3e30ce9f19d1d164d72944c878f29fc.
The private role pre-outcome fee receipt SHA-256 is
725a59a3266bcf973f38dd79007faecb839698e1cea5680eee6ddf4012c3694a;
the prior-20 receipt SHA-256 is
8f2d35065253c1025c01ae130ce69f6301094f1b6f190c58fa78392732a717c2.
Their respective candidate-cost row hashes are
1309ddc3789d29bdebd548a61bb68219afb8d957624390fe08bc1631691a0cdc
and 95c8d0817ecd749dd01a3c79e4583f64517961fe054d1a3d094eb030519cb63d.
These ignored private receipts are pre-outcome; neither is an observed return.
The new scorecard requires the previously frozen pair, matching raw market
archive, pinned source directory, and a separately collected exact venue
settlement archive no earlier than 2026-10-06 06:15 UTC.

### Historical final-result strike label preflight

On October 3, two unsigned, public historical Kalshi result GETs for one
older NFL passing-yards player prop returned the same exact contract with binary market
type, finalized status, NO result, zero-dollar settlement, one-dollar notional,
postgame settlement timestamp, exact player/team structured target, and strike
type structured. These were result-metadata reads for an older game, not
October quote collection. All 417 and 452 selected contracts in the two
October frozen prequote cohorts instead record strike type greater. The
difference may reflect API or product behavior; this single older result
does not establish how the October markets will settle.

The previous result checker required greater and would classify a corresponding
structured finalized result invalid even with exact contract, player, team,
line, rules and payout. Settlement audit v2 permits only a prequote greater
to returned structured label difference under all those exact identity and
postgame checks. It still rejects unknown or unrelated strike types. The
frozen cohorts, model forecasts, displayed asks and fee receipts are unchanged.
No result from either October cohort was fetched or scored. Recheck the full
denominators after October 6 at 06:15 UTC; any missing, nonbinary or
inconsistent result stays unavailable rather than becoming a win or loss.


### Precommitted exact-ask markout from a later retained capture

An outcome-blind, separate exact-ask markout evaluator is now frozen before
the October games. It takes the existing private pair and its matching raw
market archive, then an independently retained, complete later public NFL
market archive. For the October 3 timely pair, use the **first retained
public_daily archive after the pair completes and before the first selected
game**. Choose it by capture time, never by its prices or later outcomes.
If no such raw archive is retained, record the observation as unavailable;
do not reconstruct one from the sanitized dashboard, backdate it, or trigger
an extra quote collection for this study.

The evaluator replays each frozen role or prior-20 ask receipt, verifies both
market archives and original quote/fee context, and matches the same exact
ticker and selected side. It requires event, series, game, player, team,
prop, line, rules, strike type, and scheduled start to remain identical.
A later quote counts as a prelock markout only when its receipt is after
the frozen decision and before the existing one-hour board lock. Missing
tickers, changed identities, unquoted sides, insufficient displayed size,
and quotes after lock remain in the full candidate denominator. It reports
ask increases, decreases, unchanged prices, mean change, and equal-game mean
on the matched subset, with source and row hashes. It never selects a new
candidate, calls the provider, calculates a fill or closing line, or claims
ROI, a win rate, or an edge. A later higher ask is only a directional price
observation, not an executable resale price or profit.

Offline replay after a retained archive appears:

    python -m sportsbet.quant.kalshi_quote_markout --pair PRIVATE_TIMELY_PAIR.json --original-market-archive MATCHING_RAW_MARKET_ARCHIVE.json --later-market-archive FIRST_LATER_RETAINED_DAILY_ARCHIVE.json --policy role --output PRIVATE_EXCLUSIVE_MARKOUT_REPORT.json

Run the same command for prior20 with a separate output file. Keep the
126-candidate policy denominators separate even if their matched subset
differs. The October 2 archived quote and October 3 timely quote are about
18 hours apart but the former predates the pair decision, so their movement
is a predecision volatility diagnostic and **cannot** be passed off as this
forward markout. On the 126 October 3 role candidates, 118 exact earlier
tickers with matching identity had displayed selected-side asks in that
October 2 archive: 21 rose, 36 fell, 61 were unchanged, and eight selected
tickers were absent earlier. The mean selected-side change from that old
quote to the frozen quote was -0.00568. This check uses only retained
archives and no new provider request. It is neither a prospective markout
nor evidence of profitable predictions.


### Independently pinned private artifact restore

The retained October 3 pair ZIP was hashed before the games. Its SHA256 is
`a66bd1f486d344001bed3e5a2b95014ff31efec83e87ef02eaf26f7396721f73`.
`kalshi_pair_artifact_read.py` now requires that external digest before it
reads or restores the ZIP. It bounds the compressed and expanded sizes,
requires the exact 11-file allowlist, rejects extra, duplicate, encrypted,
symlink and non-deflate entries, checks each inner file hash, and then replays
the frozen market cohort, v3/v4 model, source manifest and both ask policies.
It writes only allowlisted files to a new explicit output directory after all
verification passes; it makes no network or settlement request.

A real offline restore of the retained ZIP on October 3 produced the original
v3 forecast hash
`99d1ff1482845c94d6f4d71eee87fa11ea40e46069eb21fcc128bb1d7449bc0a`,
with 11 files and the original selection SHA256
`a0ba727ebf86e766967db4c97ffdbe0c746ddc5ff8048a73e1648a37c939e4ce`.
This confirms portability and integrity, not game outcomes or edge. Keep
the restored player-level files in an ignored private directory:

```sh
python -m sportsbet.quant.kalshi_pair_artifact_read --archive PRIVATE_TIMELY_PAIR.zip --expected-sha256 a66bd1f486d344001bed3e5a2b95014ff31efec83e87ef02eaf26f7396721f73 --output-dir .local/verified-timely-pair
```

The restored `pair.json`, `market-archive.json` and `sources` directory
can then be referenced by the independent-series manifest after the separate
exact-ticker postgame settlement archive exists.
