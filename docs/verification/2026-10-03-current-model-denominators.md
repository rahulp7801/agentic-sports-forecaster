# Current-model performance denominator, 2026-10-03

Read-only deployed `/api/metrics` and `/api/picks` inspection around 06:45 UTC found:

| Sport | Cohort | Settled | Pending | Distinct settled games | Recorded-stake ROI |
| --- | --- | ---: | ---: | ---: | ---: |
| NFL | Current-model accepted recommendations | 1 | 0 | 1 | +80% |
| NFL | Current-model eligible predictions | 256 | 0 | 1 | -5.18% |
| CFB | Current-model accepted recommendations | 0 | 0 | 0 | unavailable |
| CFB | Current-model eligible predictions | 48 | 108 | 1 | -11.83% |
| NBA | Current-model accepted recommendations | 0 | 0 | 0 | unavailable |

The accepted NFL row is Jaylen Warren under 3.5 receptions at -125, captured 2026-10-01 01:27:52 UTC before the 2026-10-02 00:15 UTC game. The public pick ledger reports a verified win at three receptions and the read-only NFL game-log endpoint returns three receptions for the exact player and game. The reported +80% is the hypothetical unit return for **one** winning pick; it is not an estimated repeatable return, a 75% win-rate demonstration, or an authenticated independent audit of the hosted settlement transaction. Same-game forecast rows are correlated, so 256 NFL predictions and 48 settled CFB predictions still represent only one settled game each. Game-level uncertainty intervals are unavailable. The accepted NFL cohort has no closing-line observation.

The consumer evaluation view now displays the distinct-game denominator beside settled and pending counts and calls out one-game samples. Model versions, frozen evaluators, qualification rules, source chronology, quote collection, API caps, and reserves are unchanged. Verify production rendering only after its protected PR is merged and deployed. Continue collecting naturally scheduled, pregame market-matched receipts and authenticating results across independent games before any edge claim.

## October 3, 11:09 UTC scan checkpoint

The deployed aggregate `/api/scans` response recorded its latest paid scan at
about 07:10 UTC. NFL had 14 eligible games and CFB had 54; **all 68 were
deferred** with the recorded reason `rolling_credit_limit`. Both leagues had
zero completed events, paid quotes, selections, and model estimates in that
scan. NBA had zero eligible games. The three `/api/prop-screens` responses were
stale with zero comparisons and `execution_ready=false`. `/api/picks` reported
zero current picks for all three sports. The last natural paid workflow run was
[37105308795](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37105308795)
at 07:07 UTC; no new collection was dispatched for this check.

The current-model accepted-recommendation metric remains one settled NFL win
from one distinct game, with no CFB or NBA accepted settlement. It supplies no
repeatable market-edge estimate. The consumer empty board now places its
existing last-recorded scan report immediately below the no-pick message so
this collection limitation is visible without changing the 20-credit daily or
450-credit rolling caps, staged reserve, model, or qualification gates. A
newer scan or a recovered allowance is required before claiming current quote
coverage; this checkpoint does not predict when credits return.


## Conditional rolling allowance estimate in the private release

A read-only ledger projection now finds the first UTC midnight when the usage already
recorded in the inclusive 31-date rolling window would leave room for one event
check. The scan records it only when an attempted reservation fails for
rolling_credit_limit. The public status parser accepts a bounded midnight
timestamp only with a complete, recent rolling-limit report; the consumer card
labels it an estimate and says new usage, the daily limit, worker timing, game
availability, and quote availability may delay collection. It is not a
scheduled scan, a promise of credits, or a qualified pick. No reservation,
limit, pregame holdback, provider request, or qualification rule changes.
The last deployed October 3 scan predates this private release and has no
projection.
