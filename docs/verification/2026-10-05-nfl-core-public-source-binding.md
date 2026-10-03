# NFL core history public/source binding

## Reproduced failure

At private head `e8ce627`, a local synthetic row with the genuine Python
commitment for **240 passing yards** passed `nflCoreHistoryPayloads` while its
public payload returned **900 passing yards**. The existing digest check proved
the retained source row but did not bind the displayed values to it. That same
core response exposed touchdown and receiving values outside this route's proof.
This was a validator reproduction, not evidence that production returned that
fixture or that any actual forecast was wrong.

## Repair

The core validator now requires the exact player ID from the bound request.
The returned player ID, team, passing yards and rushing yards must agree with
the verified retained row. A disagreement fails the whole request closed.
After verification it constructs a limited public projection: public matchup
metadata and those two supported stats. Uncommitted touchdowns, receiving stats
that require separate reconciliation, private source columns and future view
fields cannot widen this response. Neither source rows nor model metadata reach
the browser. Null statistics stay unknown; an actual recorded zero stays zero.

Current and legacy Python row commitments remain supported. The receiving
route, frozen model/evaluator, eligibility gates and probability are unchanged.
Invalid rows retain the existing generic 503/no-store behavior, without exposing
source data. The API also retains bound date and observation cutoffs.

## Verification

- Complete frontend suite: **332 passed**. Added regressions exercise exact
  athlete/stat binding, projection boundaries and Python-golden null/zero rows.
- TypeScript, changed-file lint and the production Webpack build passed.
- **Nine actual loopback HTTP cases** passed through that production build with
  a disposable PostgreSQL view and a SELECT-only `sportsbet_dashboard` role:

| Case | HTTP result |
| --- | --- |
| Matching current and legacy commitments | 200, exact passing/rushing values |
| Contradictory payload, wrong source player, stale digest | 503, no-store |
| Explicit unknown passing stat and recorded zero rushing stat | 200, unknown omitted and zero retained |
| Before source availability and before the game date | 200, no rows |
| Core request without identity/cutoffs | 400, no-store |

The retained local result is `.local/core-binding-http-results.json`; fixture
setup/check scripts are ignored local verification artifacts. These are synthetic
fixtures, not actual picks, outcomes or evidence of market alpha. No external
requests, quote collection, purchases or bets were made.

The existing private PR #345 carries this reviewable increment. Hosted CI and
protected deployment remain blocked by the verified GitHub account gate. Local
API behavior does not imply the hosted release has deployed. Tonight's scheduled
fee/quote/anchor and tomorrow's frozen result/primary/net scoring checkpoints
remain intact; do not duplicate those observations or read results early.
