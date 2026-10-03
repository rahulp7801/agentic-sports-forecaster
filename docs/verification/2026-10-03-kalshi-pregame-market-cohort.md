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
