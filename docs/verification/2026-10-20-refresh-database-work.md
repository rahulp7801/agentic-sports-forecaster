# Reduce repeated history and settlement database work

## Observed daily evidence

The October 20 ordinary `public_daily` run on `b25b13e` reported a completed NFL
history refresh and an NBA history failure with SQLSTATE `57014`. Its NBA public
input was observed, with 54 profiles and 13 unavailable among 67 identities;
NFL reported 29 profiles. These are producer results for this invocation, not
independent profile database readbacks or proof of a particular earlier fix.

NFL settlement failed with `QueryCanceled`; its SQLSTATE and inner stage were
not logged. NBA settlement stayed blocked by the failed history refresh. The
separate CFB history stage also reported `57014`. One exact CFB snapshot receipt
was verified, but the main snapshot readback later failed with `08006` and no
completed-main count. The application access verifier was not reached. The
earlier daily invocation was cancelled without a completed producer report.

SQLSTATE `57014` establishes query cancellation, not its trigger. The failing
query, execution plan, server load and cancellation cause remain unverified.
The changes below address verified redundant work and a diagnostic gap; they do
not establish that the production failures have recovered.

## History replay guard

The common history upsert gains an explicit opt-in to skip a conflict update
when its existing preserved-observation predicate says every effective supplied
value would remain unchanged. Only the current NBA primary and CFB season
writers enable it. Default behavior and other callers remain unchanged.

The guard retains the old source bundle and first observation on identical
replays. Real corrections, changes outside the core stat hash and missing old
observation metadata still take the existing update path. Participation storage
still runs in the NBA transaction. Existing CFB revision protections continue to
apply. PostgreSQL can still lock conflicting rows before rejecting an update;
this does not eliminate lock waits. Some existing revision triggers already
reject unchanged updates, so the avoided work depends on the table and trigger.

## Live settlement read

Each existing bounded prediction batch now reads payload and all six prior raw
outcome fields together. It no longer repeats a raw-state SELECT per prediction.
The independent proof check, version precedence and guarded write are retained.
All six nullable prior values still participate in the compare-and-swap; a
concurrent change must fail the write and roll back the transaction. The frozen
ledger implementation and settlement evidence protocols remain unchanged.

## Safe failure metadata

Caught daily settlement failures now retain the existing bounded `error_fields`
output and emit one of three fixed diagnostic stages: ledger initialization,
settlement or publication. Only sanitized exception type and an available valid
five-character SQLSTATE are included. SQL, parameters, exception text, database
URLs and credentials remain excluded. Existing failure status, blocked-history
behavior and publication rules are retained.

## Verification and remaining gates

Regressions cover unchanged replay, real corrections, preserved chronology,
version/participation behavior, bounded batch reads and concurrent raw-state
changes. PostgreSQL assertions must run on the disposable CI database; local
skipped PostgreSQL tests do not count as passing database evidence. Real Linux
backend, security, frontend, CodeQL, migration and database checks remain required
before protected merge, followed by the actual hosted and production gates.

The next ordinary daily run must provide its own history/profile status,
authenticated final-stat evidence and exact snapshot readbacks. Missing or
partial counts remain unknown. No additional quote collection, retry policy,
timeout increase, role grant, model/qualification change or raw-evidence upload
is introduced. These fixtures do not demonstrate a prospective betting edge.
