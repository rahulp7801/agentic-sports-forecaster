# Collection status and provisioning diagnostics

## Fail a refresh when every schedule source is unavailable

The schedule publisher already retained the previous snapshot when all source
requests failed. Its CLI nevertheless exited successfully after printing
`unavailable`, allowing the scheduled workflow to report a successful CFB
refresh without new data. The CLI now exits with status 2 for this result.
Complete, explicitly partial and recently cached slates retain their existing
success behavior. Unexpected publication statuses also fail.

The regression exercises the real publication path with failed source results
and verifies that it writes no new snapshot. Source requests, cache timing,
qualification policies and frozen model versions are unchanged.

## Identify provisioning failures without disclosing provider data

Waitlist provisioning previously reduced every rejected Vercel request to the
same generic message. Errors now identify a fixed operation label and a bounded
HTTP status. Unknown operations and invalid status values use fixed fallbacks.
The implementation does not read the error body or include provider URLs,
reasons, headers, payloads or credentials, and suppresses exception chaining.
Ambiguous secret creation is never retried. Existing create-only behavior and
project, plan, role and permission checks remain enforced.

Tests inject randomized private values into every provider-controlled error
field and verify that neither the CLI nor a formatted traceback discloses them.
They also verify that no error body is read and no request is retried.

## Verification and release state

The combined offline suite passed: **77 passed, 22 skipped** across
`test_waitlist_provision.py`, `test_schedules.py` and
`test_workflow_configuration.py`. The skips require disposable PostgreSQL;
the required PostgreSQL CI job exercises that gate. Fresh required CI and
CodeQL checks must pass before this increment merges.

The preceding production release passed schema 0048 and bounded waitlist
provisioning. Deployment remains stopped before publication because the
production GitHub OAuth client ID and secret are absent. This increment does
not bypass that access gate or establish a forecasting edge.
