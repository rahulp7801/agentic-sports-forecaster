# Offline NFL public-quote identity coverage

The kalshi_identity_coverage diagnostic measures whether a captured public
Kalshi prop quote can be paired with a unique name and captured team in a
pre-quote NFL history snapshot. It counts historical stat rows needed to consider
a future model study. It does not run the model, accept a pick, assert settlement
equivalence, calculate returns, or publish player details.

Run only against a secret-scanned market-watch archive and a private source
snapshot captured before the market archive:

    python -m sportsbet.quant.kalshi_identity_coverage \
      --market-archive PRIVATE_MARKET_ARCHIVE.json \
      --history-snapshot PRIVATE_SOURCE_SNAPSHOT.json \
      --output PRIVATE_AGGREGATE_REPORT.json

Keep the source snapshot and resulting report private. The output is aggregate
only. The command makes no network or database request and refuses to overwrite
an existing report.

The audit verifies the market archive evidence digest, complete NFL Kalshi
discovery, one captured season, exact quote/game/team/kickoff links and quote
capture times. It excludes source rows observed after the quote, snapshots
captured after the quote, and rows lacking a distinct past game in the archived
NFL schedule. Names are normalized conservatively and must map to exactly one
current-season player ID on the captured team.

The necessary_history_present count means at least 20 non-null prop-specific
rows, including two current-season/current-team games and older history. It is a
coverage ceiling: current roster status, complete participation, model
probability, contract payout rules, matched market price, authenticated
settlement and prospective performance still require separate verification.
The report always sets target_verified, promote and execution_ready false.
It does not affect the sportsbook scanner, frozen candidate protocols,
qualification thresholds, credit caps or pregame reserve.
