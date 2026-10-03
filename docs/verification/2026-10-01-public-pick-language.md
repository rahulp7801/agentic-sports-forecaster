# Public pick wording

A live recorded NFL pick on 2026-10-01 exposed two imprecise phrases in its
stored trade plan: a model-minus-implied probability difference was printed
as a percent "edge", and a model-derived paper bankroll fraction was called
an "approved research stake." The former is a difference in percentage
points; the latter has no prospective profitability validation.

Future scan text now calls the value a model probability minus market implied
probability gap in percentage points and calls any fraction unverified paper
sizing. The read-only pick-board projection clarifies the two exact legacy
phrases without modifying the source row, receipt, price, probability,
qualification, stake fraction, or settlement. No model or evaluation version,
provider call, daily or rolling credit limit, or reserve rule changes.
This is a wording correction, not evidence of a positive edge.

## Recorded slip selections, October 4

The read-only slip builder receives **recorded or locked** board selections,
whose original prices and roster checks may have expired. Previously it
selected a "best slip" automatically on load and titled these rows
"Suggested picks," despite the separate live shortlist withholding expired
quotes. It now starts empty, requires an explicit build or add action, and
labels the pool and resulting slip as research using recorded picks that need
current line, price and availability checks. Its underlying candidate
identity, rank, probability, dependence warning, payout arithmetic and
no-order boundary are unchanged. This does not refresh any market price,
create a qualified pick or establish profit.

The local frontend suite passed 318/318, TypeScript and changed-file ESLint
passed, and the production Next build completed. Production behavior still
requires the protected private release to pass hosted CI and deploy.
