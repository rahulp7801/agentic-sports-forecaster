# Exact CFB slate publication receipts

## Observed verification gap

Scheduled free runs on current master successfully published the CFB slate,
but logged only its status. The exact database receipt gate checked four
NFL/NBA market and schedule snapshots; it never read `slate:cfb`. A successful
CFB status was therefore not proof that the consumer database held the
intended capture. CFB-only dispatches also skipped the deployed-site gate.
No incorrect CFB write was demonstrated by this audit.

## Correction

The schedule CLI can now write a metadata-only report containing
`slates.cfb.captured_at`. It retains the exact timestamp from the original
published object, or the original recent cached object. It does not reconstruct
a receipt from the current clock or a later database read. Unavailable
publication still fails and writes no new receipt. The existing cache admission,
partial-status handling and string-return API are preserved.

Both receipt readers now map `slates` to the actual `slate:<sport>` snapshot
key. The public workflow separately verifies the original CFB receipt through
the existing restricted, read-only database connection after CFB publication
succeeds, including CFB-only runs. This check also executes when a preceding
NFL/NBA collection failed. A stale or missing `slate:cfb` cannot be substituted
with `schedule:cfb`. The deployed owner-access check now also covers CFB-only
runs without requiring a nonexistent NFL/NBA report.

No source collection, quote requests, paid quota, cadence, model, qualification
policy, frozen research file or access control is changed. Receipt files remain
on the runner; no raw-evidence upload is added.

## Verification checkpoints

Regressions cover original fresh/partial/cached capture identity, unchanged
collection/read counts, unavailable publication, invalid receipt/write failures,
missing/stale/wrong-key database rows, the existing four receipts, and CFB-only
workflow eligibility. A producer-to-verifier test exercises the real schedule
CLI and checks its generated receipt against the exact stored slate.

The combined offline Python suite passed **49 tests**, and the standalone Node
production-readiness suite passed **8 tests**. Independent producer and workflow
reviews found no actionable issues. No source collection was run for these tests.

Require fresh CI and CodeQL before merge. The next already scheduled free run
must log an exact CFB slate receipt in addition to its NFL/NBA receipt count.
Do not dispatch redundant collection to obtain that evidence. Live deployment
remains held for the existing GitHub OAuth configuration dependency; this source
verification change does not establish a forecasting edge.
