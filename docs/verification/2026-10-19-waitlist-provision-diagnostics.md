# Waitlist provisioning failure diagnostics

## Observed failure

Postmerge CI [39277992950](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/39277992950)
ran at `7bf6a5df41b670cd840d2416c8ebb888f6abea44`. Its eight code and
analysis checks passed. The hosted schema plan reported current at
`2026-10-19T15:40:06.4171532Z`, the head check passed at
`15:40:07.3978130Z`, and the restricted transaction read passed at
`15:40:40.5855085Z`.

The dedicated waitlist provisioning step then emitted its generic unexpected
failure message at `15:40:56.3314781Z` and exited 1. The log contains no
exception class, SQLSTATE or failing provisioning operation. Its duration does
not identify a provider timeout or a database failure. It also cannot establish
whether this attempt created or committed a role. No repair or rotation is
justified by that message.

The release comparison emitted `deploy=false` and
`frontend_source_unchanged` at `15:40:16.3138171Z`; its enclosing job was
cancelled. Both deployment jobs were skipped. Owner authentication and
unchanged-access checks were not newly exercised. The already verified public
preview remains a separate proof.

## Change

The provisioner now emits one bounded `waitlist_provision` failure record before
re-raising the same exception. Fixed stages distinguish configuration, provider
setup/team/project/identity, environment metadata, connection/schema/role reads,
existing-role verification, and each new-role publication boundary. Clean
connection close and CLI argument/output failures have separate stages.

Records contain only schema/operation/stage, a bounded exception class and an
optional five-character SQLSTATE. Exception messages, notes, tracebacks, tokens,
URLs, SQL, parameters and provider response bodies are not included. Existing
fixed error text and failure exit codes remain in place. Diagnostic output
failure cannot replace the original operation failure.

The protected migrations-only environment loads the stdlib diagnostic helper
from the checkout's fixed `src` path. CI verifies this in a separate isolated
interpreter with protected execution disabled, before any external operation.

## Verification and limits

Synthetic failure tests cover actual provider request boundaries, database and
publication boundaries, preserved exception identity, redaction and absence of
retries or later side effects after failure. Existing real PostgreSQL tests
continue to verify privilege drift rejection, rollback, no credential rotation
and ambiguous publication handling. The migration-only import smoke remains a
real CI gate.

The local focused suite passed 150 tests, with 22 disposable-PostgreSQL cases
skipped and one unrelated real CFB CLI case deselected on Windows. Both remain
in the required CI suites. The exact new isolated migration-only smoke passed
locally using the locked migration dependencies and bundled Windows driver;
the existing Linux CI smoke also exercises its configured pure Python driver.
An independent source review found no changes to external calls, SQL, timeouts,
privileges or credential behavior. Required CI and hosted results must still
be read from the actual release runs.

Provider endpoints, request counts/order, TLS checks, connection/query/lock
timeouts, SQL, privileges, credential creation rules and no-retry behavior are
unchanged. This release diagnoses a subsequent failure; it does not establish
the cause of the observed failure or restore waitlist/owner-login readiness.
No extra quote collection, model or qualification change, raw-evidence upload,
original evidence rewrite or spending is involved.
