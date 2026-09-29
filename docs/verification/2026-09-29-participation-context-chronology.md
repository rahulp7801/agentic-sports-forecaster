# Forecast-time source cutoff for participation context

The scanner already supplies its selection timestamp to `historical_availability_splits`. NFL receiving history used that timestamp, but NFL passing/rushing and NBA descriptive comparisons did not consistently apply it.

The corrected query path binds the observation cutoff to:

- NFL primary stats, positive-snap tenure and per-game participant labels, across passing, rushing and receiving markets.
- NBA participant identity resolution, target statistics, positive-minute tenure and per-game minute labels. Identity records also require a pregame date and recognized source commitments.
- Existing NFL receiving supplements retain both source-observation and insertion cutoffs.

An explicit naive timestamp is rejected before querying. The no-cutoff interface remains available for legacy callers; the scanner always supplies an aware timestamp. Stored predictions are never rewritten. This change concerns descriptive evidence and does not add a probability adjustment, alter qualification gates or revise a frozen model/evaluation.

## Verification

Unit tests exercise cutoff forwarding and timezone validation. Disposable PostgreSQL regressions cover late-arriving stat rows, participation receipts, tenure and ambiguous identity. An available identity remains eligible before a conflicting later observation; once both identities are available, the comparison abstains. Existing corrected-history and shadow-model tests remain required.
