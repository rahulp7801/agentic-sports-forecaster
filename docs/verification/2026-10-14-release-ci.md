# Release CI artifact integrity correction

The first executable public CI run for PR #345 passed frontend, PostgreSQL,
worker-image and secret checks. Backend tests found six failures because
Git normalized the frozen NFL stat-only JSON artifact to LF, while its frozen
SHA-256 identifies the original CRLF bytes. The Windows working file passed
the same hash check; Linux checkout and Git archive produced different bytes.

The artifact is now explicitly excluded from Git text conversion and stored
with the original frozen bytes. Its JSON values, artifact SHA-256, model and
policy versions, implementation files, qualification thresholds and saved
research receipts are unchanged. The existing hash-integrity and replay tests
continue to enforce the original artifact; no hash or test expectation is
relaxed.

Original artifact SHA-256:
`cfcf0c9e57d3027fcc21e9a105bab03752f80c1a0b4684efa2ab7c09bbdfe35f`.

Validation: focused stat-only paper tests and Git archive byte verification.
Full Linux CI and required security analyses must pass before merge.

## Security analysis review

The corrected release passed all five CI jobs and all three CodeQL analyses.
The aggregate CodeQL result identified two findings:

- Replaced a test URL prefix comparison with exact parsed origins, retaining
  containment assertions and covering unrelated hosts, host suffix spoofing,
  userinfo spoofing and an HTTP downgrade. All 45 release-controller tests pass.
- Independently reviewed alert #6 as a password-hashing false positive. The
  SHA-256 digest only rejects one historically exposed provider API key through
  `hmac.compare_digest`; it does not store passwords, authenticate users or
  persist active-key digests. All five callers check before provider I/O; four
  tests verify no echo and refusal before ledger/network access. The original
  denylist implementation is retained. CodeQL's own guidance permits SHA-2
  outside password/limited-input-space hashing:
  https://codeql.github.com/codeql-query-help/python/py-weak-sensitive-data-hashing/

No query exclusions, reduced query suite, relaxed thresholds or disabled
branch protections were added. Fresh current-head CI and CodeQL remain required.

## Postmerge production connection binding

Release #350 merged as `0b562e1` after all required checks passed. Production
upgraded through schema0048 and its restricted transaction read passed.
Waitlist setup then exposed two configuration problems: the owner migration
URL lacked verified TLS options, and the generic pipeline DATABASE_URL is the
ingestion worker identity rather than the dashboard identity required by the
provisioner.

The existing owner credential was tested read-only against the pinned CA and
republished with verify-full, retaining its identity and password. Production
waitlist provisioning alone now binds a separate protected DASHBOARD_DATABASE_URL. Schema readiness and ingestion
keeps its existing worker credential. The strict same-project/dashboard role
checks and separate migration owner credential remain enforced.
