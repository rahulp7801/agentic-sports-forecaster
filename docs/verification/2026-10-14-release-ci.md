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
