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

## Frozen forward test

`cross-book-forward-v1` starts at 2026-09-30T00:00:00Z. The corrected NFL and CFB history models and the current NBA v4 model are evaluated separately. Captures, model generation and quotes must be at or after the freeze; history and recommendation policy identities are enforced. Changed evaluator dependencies fail closed by normalized source digest. New model identities or dependency changes require a new protocol.

Run `python -m sportsbet.quant.cross_book_forward --ledger-path PRIVATE_SNAPSHOT.sqlite3 --output PRIVATE_FORWARD_REPORT.json`. Omitting the ledger path uses the configured hosted ledger inside a read-only repeatable-read snapshot. It never requests provider quotes. The existing follow-up process can run this against naturally collected records; no paid collection or workflow schedule is added.

Forward reports retain offer IDs, reference IDs, exact source response commitments and decision times so later checks can reconstruct each selection. They exclude outcomes authenticated after the audit time. Historical experiment selections cannot enter the forward sample. A sample needs at least 50 paired settled games, 100 decided selections and 30 selection games, a strictly positive lower 95% game-cluster ROI bound, and a strictly negative upper 95% probability-error difference versus matching offered-book market prices before requesting review. Passing still never promotes a model or creates production picks automatically.

All 38 focused tests pass, including immutable dependency enforcement, freeze boundaries, policy/model separation, future receipt rejection, private selection manifests, pending settlements, and a synthetic sufficient-evidence case that still requires review. The initial forward audit was executed against the existing private archive; all sports correctly await the future start. This is code/protocol publication only; historical research metrics and artifacts remain private.

## Live source-read correction

The first hosted audit attempted to load all archived prediction payloads before applying its future-only filter and hit the read-only statement timeout. The query now applies sport, model-version and timestamp scope at the database source, as the existing history evaluators do. `CASE` isolates timestamp casts from unrelated legacy records. The repeatable-read/read-only transaction and all downstream evidence checks remain intact. No selection, model, threshold or dependency-freeze rule changes.

Eleven forward-evaluator tests pass, including source filtering before payload transfer. The corrected hosted audit completed successfully before the freeze and reported all three sports awaiting start. No historical outcomes entered the forward sample. Production verification for PR #266 completed successfully; this small follow-up carries the source-read correction through the same CI/deployment gates.
