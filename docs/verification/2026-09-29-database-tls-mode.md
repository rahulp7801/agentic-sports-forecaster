# Unambiguous database TLS mode

## Reproduced configuration failure

The application checked the first URL `sslmode` value with `URLSearchParams.get`, while the installed PostgreSQL driver uses the last value. Without a custom CA, a hosted URL ending in `sslmode=verify-full&sslmode=disable` passed the application check and produced a driver configuration with TLS disabled. A last `no-verify` value disabled certificate verification. This is a deployment-configuration boundary, not a demonstrated public-request exploit.

## Change

Hosted connections and connections with an explicit CA require exactly one `sslmode=verify-full`. Duplicate modes, including percent-encoded parameter names, fail before driver construction. Valid public-CA and custom-CA connections preserve certificate and hostname verification. Local development can still explicitly use plaintext.

The change does not inspect, print or modify production credentials. It changes no API collection, spending, model, threshold or frozen evaluation. PR #194 remains excluded.

## Verification

The duplicate-mode regression fails before the fix and passes afterward. Tests construct the installed real `pg.Client` without opening a socket, verify the effective SSL configuration with and without libpq compatibility, and verify custom CA preservation. All four focused database configuration tests pass locally. Required frontend tests, lint, type checking, build, audits and repository CI must pass before merge. After deployment, verify normal read-only public API responses and malformed-request rejection.
