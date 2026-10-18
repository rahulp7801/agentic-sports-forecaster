# Identify hosted schema and read failures safely

## Observed gap

The production schema gate on merged releases `0eab4394bb5753dac57b2cdf617a71507102e72f` and `7d909c8b2e00b953122482f6541d7de75c448919` failed during `Plan hosted schema using restricted transaction reader`. Both logs retained only `Hosted transaction-pool schema/read preflight failed`. They do not identify the failed operation or its underlying SQLSTATE. Later hosted checks and deployment jobs were skipped.

A subsequent ordinary public monitor on `7d909c8` passed its schema-head check and independent publication receipt checks. That separate success does not explain the earlier production preflight failure or establish lasting database health.

## Change and boundaries

Add a finite failure stage and bounded exception type/SQLSTATE to this existing preflight. Do not print exception messages, credentials, URLs, SQL, parameters, tracebacks or exception notes. Preserve the generic CLI failure message and nonzero exit. A diagnostics failure must not replace the original failure.

Keep the current migration planning, missing-version-table behavior, exact migration-head comparison, restricted read queries, TLS validation, existing Supabase transaction-port mapping, connection options and success output. Do not retry connections, request additional credentials or weaken any release gate. The script must also run with the existing migrations-only dependency group, without requiring worker dependencies.

## Verification and next checkpoint

Exercise failures in configuration, migration-head discovery, connection, schema read, dashboard read, connection cleanup, schema comparison and output writing. Check redaction, preserved exception identity, one diagnostic per failed invocation, unchanged missing-table planning, and direct-script execution without an installed application package. The existing TLS and single unprepared read tests remain required.

The focused local suite passed 71 tests with no failures. It disabled global fixtures and plugin loading, and deselected one unrelated CFB CLI integration test after an earlier broader run stalled there. The required full CI suite still includes that integration test. A separate isolated smoke passed using the locked migration-only packages and the bundled Windows driver. The pure Python driver lacks a local Windows `libpq`; Linux CI retains its existing pure Python driver and runs the same smoke with its actual migration-only environment. That smoke requires a missing database URL to produce the exact redacted configuration failure before database access; it does not substitute for the hosted schema/read gates.

After all required CI and final CodeQL checks pass, merge through the normal protected branch. Inspect the actual postmerge production schema job for its result and, on failure, its recorded stage/type/SQLSTATE. Do not infer an infrastructure cause from a generic failure or one successful probe. Deployment remains subject to the existing authentication, containment, hosted checks and free quota checkpoint; this change does not dispatch a deployment or collection run.
