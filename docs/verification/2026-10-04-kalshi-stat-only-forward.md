# October 4 NFL stat-only Kalshi forward paper receipt

This private research transfer was frozen **after** the `nfl-stat-only-shadow-v1`
2026-10-04 00:00 UTC cutoff and **before** every selected NFL game. It does not
change the frozen sportsbook paper evaluator, production model, qualification
threshold, API budget, reserve, or dashboard picks. It is a separate Kalshi
settlement population and its displayed asks are unfilled prices.

## Fixed provenance and chronology

- Original timely Kalshi pair: 2026-10-03 13:03:52–13:03:53 UTC, 452 exact
  contracts, 308 source-backed role forecasts. Its retained source/quote
  artifact is hash-replayed before this transfer. The transfer uses its 233
  receiving-yard and reception forecasts as the fixed target-contract universe;
  no contract was selected by the October 4 price or by a game result.
- Historical nflverse player-stat/snap source bytes and release metadata are
  pinned in that pair's source manifest. The older official `games.parquet`
  schedule asset 607460864 was retained before the original quote and has
  SHA-256 `4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662`.
  The current upstream asset has since been replaced; the exact older bytes
  are retained privately. Only team/week/gameday fields supply dates. A
  future quoted team's local game day was independently checked against the
  schedule: exactly one fixture matched for each of 144 forecasts.
- Frozen stat-only artifact SHA-256:
  `cfcf0c9e57d3027fcc21e9a105bab03752f80c1a0b4684efa2ab7c09bbdfe35f`.
  The model's coefficients and feature formula are unchanged. This transfer
  reconstructs played-game history from snap-backed nflverse rows, including
  explicit zero production when snaps prove participation. That input
  population can differ from the sportsbook paper history, so results must
  be reported under this separate protocol.
- The outcome-blind probability receipt was saved at **2026-10-04 00:28:12 UTC**:
  233 fixed receiving contracts, 144 predictions (64 receiving yards, 80
  receptions), 81 below the frozen minimum line and 8 nonmonotone candidates.
  All 15 games were still future. Forecast rows SHA-256:
  `ad74381b6d7b1707c0c6f2b5d0ab9e22e3e14d4e6eafc7145902656785837f13`.
  Receipt file SHA-256:
  `649de1f5595c2dcf789050d63d9612375b2d4cae29751943697db62a52368d58`.
- One unsigned, public Kalshi `GET /markets` observation requested the **144
  precommitted exact tickers** in eight batches, with no paid Odds API or order
  request. It completed at **00:29:38 UTC**, before the five-minute model window
  and the first one-hour pregame lock. All eight batches returned. Raw quote
  receipt file SHA-256:
  `66dea5d6c5399501f053cab255c381bf78b9d15c1bebb7f658235bad80b1275f`.
- The existing fixed 5-percentage-point gross ask rule was applied after
  validating exact ticker, event, player, team, line, occurrence time, rule
  hash, quote sides, positive size, and board lock. It selected the larger
  YES/NO gap, then at most one contract per player/game by gap and ticker.
  Decision time: **00:30:42 UTC**. Of 144 model forecasts, 102 passed the gross
  margin, 39 were below, 2 exact markets were closed, and 1 opposite side
  lacked one contract of displayed size. The player/game cap removed 32,
  leaving **70 paper candidates in 15 games** (25 YES, 45 NO). Candidate rows
  SHA-256:
  `b8750ea51d18703c9f23b67dada8d7f3939df2cf20238dd1615b598b418d4d06`.
  Decision receipt file SHA-256:
  `81646fd99f2f57cb70ec5b60a9889de93d2d86f99017ca3150b71e2c7df4987e`.

The original forecast and decision scripts replayed to **byte-identical**
receipts at their recorded timestamps from the retained raw market archive and
source files. The three original scripts, three original receipts, and exact
schedule bytes are backed up under ignored
`.local/kalshi-stat-only-forward-20261004/` in the original workspace. The
Player-level rows and raw prices are not tracked in Git. The original scripts
are preserved in the ignored backup; the private repository scorer adds a
quote-before-decision replay guard and produces the identical decision receipt.
The tracked quote script now also gates future local captures on a new clock
check; it was not part of the original October 4 quote receipt.

## Pre-result evaluation boundary

The 70 candidates are research hypotheses. Their mean frozen model win
probability was 0.6559, mean displayed ask was 0.5034, and mean gross gap was
0.1524. These are model beliefs versus displayed asks, **not** observed wins,
calibration, fills, net returns, or an edge. Twenty selected candidates use at
least one snap-backed zero, so report a sensitivity by that frozen flag without
reselecting the cohort. Current roster and game-day participation are not
verified; Kalshi's nonparticipation settlement can differ from a sportsbook.
Fees, order depth, slippage and closing prices are not established for this
new quote; ROI and CLV remain null. The previously frozen role/prior-20 ask
cohort is a different model decision on the same 15 games and cannot be counted
as 15 more independent games.

No result request occurs before **2026-10-06 06:15 UTC**, six hours after the
last selected kickoff. Then authenticate **all 452 original exact contracts**
using the bounded read-only settlement collector, retain its full denominator,
and evaluate this 233/144/70 transfer as a predeclared subset. Record every
missing, invalid, nonbinary, and unplayed state. Compare paired Brier and log
loss with the frozen prior and matching same-time market probability; evaluate
gross and fee-inclusive unit payoff only where fee terms and venue outcomes are
validated. At least 50 independent future games and favorable game/player
cluster uncertainty versus both baselines are needed before even descriptive
probability support. An executable edge additionally requires matching fees,
participation rules, fills, slippage and prospective closing-line evidence.
Qualified consumer picks remain zero here.

## Precommitted outcome scorer

`src/sportsbet/quant/kalshi_stat_only_forward_eval.py` was added before the
selected games. Its Oct4 cohort constants pin the original pair, raw market,
model, exact quote and decision **file hashes** from this note. Offline
`preflight` replays the original v3 source-backed role report, verifies the
seventh pinned schedule file and frozen stat-only implementation, validates all
144 exact quote requests and response clocks, checks each market's contract and
rule identity, and recomputes the fixed 5-point, one-per-player/game policy.
It makes no network request. On the saved inputs it reproduced the fixed
452 / 233 / 144 / 70 denominators and earliest result time
2026-10-06 06:15 UTC. The ignored preflight report SHA-256 is
`c0420181930b006b297e769f129bd280920a4915cbf9217c47e0575fb3ad9d7d`.

Run the preflight from the private repository root, with the existing retained
paths, before reading outcomes:

```sh
python -m sportsbet.quant.kalshi_stat_only_forward_eval \
  --pair .local/verified-timely-pair-20261003/pair.json \
  --market .local/verified-timely-pair-20261003/market-archive.json \
  --forecast .local/kalshi-stat-only-probabilities-20261004.json \
  --quotes .local/kalshi-stat-only-quotes-20261004.json \
  --decisions .local/kalshi-stat-only-ask-decisions-20261004.json \
  --source-dir .local/verified-timely-pair-20261003/sources \
  --schedule .local/team-share-sources/games.parquet \
  --output .local/kalshi-stat-only-preflight-again.json
```

After the bounded full-452 exact-ticker settlement archive is captured at or
after the eligible time, pass `--settlements` to the same command and a new
exclusive ignored `--output`. The collector and scorer are distinct steps.
The scorer authenticates all 452 venue states, keeps all 144 forecast and 70
paper-decision states, and computes paired Brier/log loss against the
contemporaneous two-sided midpoint and frozen unfitted prior. It reports
hypothetical **gross** one-unit payoff only for verified decisions and a full
cohort total only if every selected result is verified. ROI and CLV remain
null; fees and fills remain unverified. Probability support requires all 144
results and prices valid, at least 50 independent games, and upper 95% whole
game and player cluster bounds below zero for Brier and log loss against both
comparators. The current 15-game cohort alone cannot pass. Edge and qualified
picks stay false/zero regardless of this diagnostic result.

The same postgame report keeps a predeclared descriptive sensitivity split by
`snap_backed_zeros > 0` on each frozen forecast: **36 of 144** forecasts and
**20 of 70** paper candidates used at least one snap-backed zero. The two
fixed buckets report the full forecast and candidate denominators, paired
model/market/prior Brier and log loss where venue results and prices verify,
and verified-subset wins and hypothetical gross payoff. A bucket's full gross
payoff remains null until all its candidates verify. This split does not
reselect contracts or establish a separate edge; its 15 shared games remain
correlated.

Before any selected game, an additional fixed diagnostic was declared for the
advertised 75% individual-pick win-rate question: retain only original paper
candidates whose **frozen model win probability is at least 0.75**. This is
**11 of the 70** candidates in **8 of the 15** games, all on the NO side.
Their mean predicted win probability is **0.8014** and mean displayed ask is
**0.5245** (mean gross gap **0.2768**). These are still untested model beliefs,
not a 75% observed win rate or executable edge. The separate
`kalshi_stat_only_high_probability_eval.py` diagnostic replays the pinned
primary preflight without changing its scorer. At or after the same settlement
gate, it reports this group's entire frozen denominator, every result state,
and a full-group win rate and hypothetical gross payoff only when all 11 venue
outcomes authenticate.
A separately labeled verified-subset rate can be incomplete. Eight correlated
games cannot establish a reliable 75% win rate; this diagnostic cannot alter
the primary 70-candidate result or qualify consumer picks.

The no-result diagnostic replayed all pinned source, clock, market, model,
quote, and decision evidence before the first selected kickoff. Its selected
exact-ticker-set SHA-256 is
`b3383ce6c65abac15e17b69a8063393c75218e07ce38d6c1cd898fcac8c8c42e`;
the ignored aggregate report SHA-256 is
`f43b0eaf6ffc0f007e0d5e295733920ea74a0a89ebeeeefe9b16af9d1be6ea17`.
At or after 2026-10-06 06:15 UTC, pass the same six pinned inputs and the
authenticated full-452 `--settlements` receipt to
`python -m sportsbet.quant.kalshi_stat_only_high_probability_eval`, with a
new exclusive ignored `--output`. The pre-result run omitted `--settlements`;
its full-group win rate and profit were null. Four focused synthetic tests
passed for threshold inclusion, no early result read, missing outcomes, and
complete authenticated scoring.

Local no-result preflight passed on the retained exact files. Five focused
tests passed for hash commitment, quote/decision order, missing outcomes in
the fixed denominator, refusing a premature settlement audit, and a synthetic
postgame full-denominator path. The adjacent model, quote, venue, and scorer
suites passed 52 tests. Synthetic labels are test fixtures only; no actual
venue result has been fetched or inferred.

## Local clock evidence and future gate

The October 4 original forecast/quote/decision receipts used this Windows
workstation's UTC clock. A later `w32tm /query /status` reported **not
synchronized**, source Local CMOS Clock, and no last successful sync. This
limits how strongly those local timestamps independently prove absolute UTC.
At about 01:00 UTC, fresh nonce URLs at GitHub and Cloudflare returned HTTP
`Date` offsets of +0.48 and +0.36 seconds relative to the workstation;
a separate later check returned +0.02 and -0.07 seconds. The readable Windows
System event log showed **zero** Kernel-General clock-change events between
23:00 and that later check. Those observations support a stable clock around
the capture but **do not retroactively attest its 00:28-00:30 UTC offset**.
The posthoc raw check is ignored/private, SHA-256
`3ad37406db4ac19765e591fa9957e5f84d3500522cf40fa76019de7ebeb25545`.
The frozen model, quote, and candidate receipts and their scores were not
changed or re-timestamped.

For a **future local recovery capture**, the tracked free exact-quote script
now calls `sportsbet.quant.clock_attestation.attest` before any market request.
It makes two unsigned no-cache GETs with unique nonces to fixed GitHub and
Cloudflare hosts, follows no redirect, ignores environment proxy credentials,
and rejects missing/cached `Date`, a round trip over two seconds, an offset
over two seconds, or host disagreement over 1.5 seconds. It stores the raw
clock check in the future private quote evidence. This gate cannot be applied
to the already frozen October 4 receipt; its original quote script remains
backed up unchanged. HTTP `Date` is the response origin time and `Age` marks
cache residence under [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
and [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html). Six focused clock
tests passed, including cache, slow-response, missing-header, and unsigned
fixed-host cases; live direct TLS checks passed without a provider quote.
