# Legacy graph paid-quote credit boundary

The exported `create_graph_with_sqlite` factory could wire the older
`OddsAPIPoller` with a **500-credit default**. That poller created a fresh
in-memory remaining-credit counter for every instance, did not reserve from
the shared `Ledger`, and checked a fixed `<10` threshold before a per-event
call requesting **seven** player-prop markets. The graph context agent creates
separate pollers for game odds and props. This path is not called by the
deployed scheduled `scan` or public dashboard, but a future caller with the
existing API key could have spent credits outside the approved 20/day and
450/rolling application limits. This is a real code boundary, not a claim
that such calls already occurred. No provider call was made during this audit.

The [provider's v4 documentation](https://the-odds-api.com/liveapi/guides/v4/)
states that odds quota cost depends on requested markets and regions, and
provides remaining and last-request-cost headers. The legacy game request
specifies three markets in one region; its fixed NFL/NBA prop request specifies
seven markets in one region. The event-list call is conservatively reserved as
one credit. Actual returned-market costs can be lower; the local reservation
does not refund unused estimates.

The poller now requires an existing shared analytics database configuration
and calls the same persistent `Ledger.reserve_api_credits` as scheduled scans
**before every request**. It reserves 3 credits for default game odds, 1 for
the event list, and 7 for each event-detail prop request, plus the existing
two-check pregame holdback calculated from the sport's frozen prop-market
width (NFL 8 credits, NBA 6). Unsupported game regions, markets or prop
sports fail before network. The poller and graph factory default to 20/day;
explicit values above 20 or a configured rolling allowance above 450 fail
closed. Provider remaining-credit headers remain a second guard. A request
that fails after reservation can overcount local usage; it cannot create an
unrecorded paid request. The model, quote admission, selection thresholds,
staged scheduled-scan reserve and frozen evaluation code are unchanged.

Mocked tests establish that an empty shared ledger setting, exhausted ledger,
raised cap or insufficient provider balance sends **zero** requests; a
successful three-market game request reserves `(3, 20, holdback=8)`, and a
prop event list does not authorize its later seven-market detail when the
second reservation is refused. A temporary real SQLite ledger test starts
with 12 of 20 credits used, preserves the 8-credit holdback across two fresh
poller instances, and records no further request or usage. Construction of a
context agent with 500 credits now rejects immediately. Adjacent context,
props, credit-default and graph integration tests passed **80/80**; full
backend suite passed **2,096/2,096** with 72 skips and seven existing pandas
warnings. No live provider, payment, or wager endpoint was called.

This guard does not claim new consumer picks or an edge. It cannot compensate
for usage by other applications sharing the provider key, nor for an account
with no remaining provider quota. Production still needs the protected private
release to pass GitHub checks and deploy. The fixed free public Kalshi paper
cohort and its pregame capture schedule do not use this poller.
