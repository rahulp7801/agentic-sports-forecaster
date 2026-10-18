# Commit related market snapshots together

## Observed failures and consistency risk

Natural monitors `39152320195` and `39156149022` ran on `0eab4394bb5753dac57b2cdf617a71507102e72f`. Both reported failed NFL/NBA market components with `OperationalError`, while exact verification later accepted their two schedule receipts. Neither report contained a market capture clock; producer finish times do not replace that missing evidence.

The later CFB verification logged `published_snapshot_receipt` / `snapshot_read` / `ConnectionFailure` / SQLSTATE `08006` at `2026-10-18T19:01:29.6134395Z`. A later independent schedule read succeeded. This establishes a connection failure during that read; it does not identify the infrastructure cause or the SQLSTATE of the separate market failures.

Code review found a concrete consistency risk: after saving its local archive, the collector committed the Kalshi identity handoff and market summary in separate transactions. The first write could commit before the second failed. An escaping publication exception also prevented the collector from returning its summary/archive to its caller. The saved logs do not establish which publication failed or prove successful source collection.

## Change

The collector prepares both payloads once from the same original capture and publishes the pair through one bounded batch in one database transaction. All payloads are serialized before acquiring the engine. Distinct parameterized keys and the existing JSON encoding are retained; malformed or duplicate batches fail before database access. Existing single-snapshot callers retain their current behavior.

A statement failure rolls back the whole pair. Loss of the commit acknowledgement can leave both rows committed; that outcome remains failed/uncertain and is not automatically retried. The collector and archive are not replayed. Database endpoints, TLS, privileges, timeouts, collection budgets, source clocks, evidence hashes and qualification rules are unchanged.

Publication failures emit the fixed `market_watch` / `publication` diagnostic, and the handled daily market result retains the bounded error type and SQLSTATE. Failed components do not gain a fabricated capture clock, source-success claim or successful publication receipt. Raw archives remain local.

## Verification

The focused local suite passed 264 tests; four PostgreSQL cases skipped because no disposable database was configured locally. Coverage includes serialization before I/O, exact payloads/clocks, single collection/archive/batch calls, failure and commit-acknowledgement propagation without retry, original cadence/credit guards, and strict report/receipt contracts. Independent source review found no remaining must-fix issue.

The required PostgreSQL CI job includes a real two-row rollback/commit test: the second JSONB value is rejected, both previous rows and timestamps must survive unchanged, and a valid pair must then commit with matching database transaction timestamps. That actual CI result is required before merge, together with the remaining required checks and final CodeQL aggregate. A cancelled initial local run used persistence fixtures that had not yet been adapted; the stated result is from the corrected complete rerun with local-only database configuration.

## Next checkpoint

Inspect the next natural monitor on the merged release for its exact cron/selected operation, actual market status and original capture clocks, fixed publication diagnostic if present, and each actual database verification result. A success must come from those observations. Atomic publication alone does not prove that intermittent connections recovered, that NBA profile inputs were accepted, or that picks have a prospective edge.

The contained public landing release still requires its real hosted checks and the recorded free-deployment cooldown. Owner authentication separately requires GitHub OAuth setup. The original `D:` evidence remains subject to drive recovery; this release does not read or rebuild it.
