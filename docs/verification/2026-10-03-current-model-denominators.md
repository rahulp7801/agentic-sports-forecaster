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
