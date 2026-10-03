# NBA model source cutoff through the consumer pick board

The new NBA source-as-of model records history_observed_before at model
selection. Its Python board eligibility checked that field but the board
serializer discarded it. The browser requires that exact cutoff for the
new model version, so an accepted NBA selection could be rejected during
public pick-board validation before it reached the dashboard.

The accepted board now retains the recorded cutoff only for the new NBA
version. The browser's public projection already validates the version,
policy, quote-to-source-to-forecast order, and pregame time. The card and
evidence-panel game-log requests now use the model-selection cutoff; the
later immutable forecast write can no longer widen the displayed form
cohort. The stable card snapshot retains the model version, policy, and
cutoff so the request and formatter use the same source-time window.

This repairs publication and descriptive context, with no new pick, model
probability, qualification threshold, source row, market quote, provider
request, credit, bet, or frozen evaluation change. It does not prove a
profitable edge or make the still-blocked private release live.

Verification at this change: 2,028 backend tests passed, 72 skipped;
299 frontend tests passed; TypeScript, changed-file lint, and production
Next.js build passed. Focused tests pass 39 Python and 36 frontend.
The Python test checks the accepted board retains its exact source cutoff;
the browser test accepts that new-version board and rejects a missing or
pre-freeze cutoff; the card test checks the query uses model selection
rather than the later forecast write. The full frontend run initially
exposed a payout-only test that implicitly used the current wall clock
and old v4 version. It now fixes its historical model-era clock; the
payout implementation did not change.

Protected CI, schema migration, deploy, and a fresh live NBA eligible-game
scan are still needed before production verification. The current deployed
site has zero eligible NBA events and no current NBA picks.
