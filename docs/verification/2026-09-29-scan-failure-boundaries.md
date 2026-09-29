# Scan failure boundaries

## Observed issue

A recorded daily run reported a database OperationalError after quote ingestion and model queries. Its report did not identify the failing database operation. The available logs do not prove the underlying connection failure's cause. Later scheduled scanning recovered.

Code inspection found that cache reads, cache claims, budget reservation, and the pre-request checkpoint were outside the event exception boundary. A cleanup exception could also replace the original model or publication exception and abort remaining events.

## Change

- Include pre-request database operations within the event failure boundary. A failed event is recorded and later queued events can proceed under the existing budget.
- Release owned cache leases once in a finally block. Record cleanup failures separately without replacing the original failure or relabeling a successfully published event as failed.
- Retain a degraded scan status whenever either event work or cleanup fails.
- Record fixed operation labels and validated five-character SQLSTATE codes. Do not include exception messages, SQL statements, query parameters, connection strings, or provider URLs.
- Fatal scan errors remain errors, with an operation label in worker logs. Pool cleanup is attempted even if cache disposal fails.

No failed writes or provider requests are retried. Uncertain credit reservations are not refunded. The daily and rolling ceilings, staged pregame reserve, frozen model versions, and qualification gates are unchanged.

## Verification

Regression cases inject database failures in cache reads, credit reservation, pre-request checkpoint, successful-event cleanup, failed-event cleanup, and aggregate publication. They check continuation, original error retention, degraded coverage, bounded request counts, credential redaction, and pool closure. Local diagnostic tests pass; the full dependency-locked CI suite is the release gate.

## Follow-up

Inspect the next scheduled scan's failure operation and SQLSTATE if a database failure recurs. Do not trigger extra quote collection just to exercise the new diagnostics. An absence of new errors alone does not establish the original connection failure's cause.
