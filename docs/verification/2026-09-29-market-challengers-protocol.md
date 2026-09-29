# Chronological market challengers

Offline research only. No promotion, provider calls, quote collection, production writes, changed qualification thresholds, or bets. Reports remain local/private; do not upload CFB or team-context research reports as repository files or CI artifacts.

## Fixed experiment rules

Use retained source-verified half-line forecasts with at least 20 historical observations and zero push mass. Reproduce a same-book no-vig baseline from verified opposite-side evidence. A fallback opposite receipt must share the exact quote identity and source-response hash and already be available at entry. Reject missing/conflicting prices. Collapse duplicate sides/books to the earliest player/game/market/line observation for probability comparisons. Pending or unauthenticated settlements never become losses or training labels.

Compare the recorded model, the matching market, an 80-observation market prior, and a convex model-versus-market residual weight fitted strictly from previously authenticated outcomes in other games. Require five earlier settled games. Give each game equal training weight, then each player within the game, then each line within the player. Fit the residual weight analytically within [0,1]; do not select parameters from the reported evaluation outcomes.

The separate cross-book experiment uses other books from the same retained source response and exact player/game/market/line. It excludes the offered book from its reference median. Both the offer and references must be at most 300 seconds old when all required receipts are available and must precede kickoff. Reject ambiguous book-side prices. Select at a fixed estimated return of 2% or greater, at most once per player/game: earliest qualifying batch, then highest estimated return at that instant, then stable record identity. This is an experimental selection rule, not a production qualification rule.

Score Brier error against the matching market on exactly the same observations. Report hypothetical equal-stake returns separately, with pending counts. Resample entire games 10,000 times with seed 20260929 for uncertainty; fewer than two games cannot yield a between-game interval. Repeated players across games remain a limitation. A favorable subgroup or an interval from a small sample cannot establish an edge.

## Reproduce

Run `python -m sportsbet.quant.market_challengers --ledger-path PRIVATE_SNAPSHOT.sqlite3 --output PRIVATE_REPORT.json --sport all`. The input must already exist; SQLite is opened read-only with query-only enforcement. Reports contain the input-file and implementation hashes. There is no network collection or database configuration requirement.

These archived outcomes were already inspected. Chronological fitting prevents future labels entering each forecast, but this historical exploration is not an untouched confirmation set. Subsequent forward evaluation must use a separately frozen protocol, future captures, model identities and prospective thresholds.

## Verification

The targeted challenger, exact-baseline and priced-audit tests pass (27 tests). They exercise genuine quote proof, forged proof rejection, future opposite receipts, unverified outcomes, past-only fitting, equal player/game training weights, duplicate suppression, same-line/source constraints, stale and post-kickoff quotes, own-book exclusion, ambiguous prices, one selection per player/game, missing labels, clustered uncertainty, and read-only file enforcement. No private replay metrics are included in this document.
