# Independent daily publication checks

## Observed failure

Scheduled public-daily run `38772398923` successfully completed the NFL/NBA
update and the exact CFB slate receipt check. Free CFB settlement then returned
`degraded` because final-stat evidence was incomplete. This is an intentional
nonzero result that preserves unresolved forecasts.

GitHub Actions applied its implicit `success()` condition to the later player
profile and NFL/NBA receipt/site checks. Both were skipped even though their
own source producer had succeeded. The missing-stat condition in CFB could
therefore prevent unrelated source-backed profiles from refreshing and hide
the verification result of an otherwise completed NFL/NBA publication.

## Correction

The main public update now has a step ID. Profile and receipt/site steps use
explicit status guards that require an uncancelled run, successful worker
configuration and schema checks, and their own successful producer. NFL/NBA
readiness depends on the main update; CFB-only readiness depends on the CFB
slate publisher and still skips the absent NFL/NBA report.

A CFB settlement failure remains a failed step and a failed overall job. No
`continue-on-error` is added. A failed profile refresh also remains visible
while the independent receipt/site check can still run. The existing private
access check and exact receipt comparison are unchanged.

No extra collection, quote requests, scheduling, credit limits, credential
scope, model policy, frozen research file, settlement criteria or raw-evidence
upload is introduced. Missing final stats remain unresolved until independently
verified source evidence supports grading them.

## Verification

The focused workflow and local-only evidence tests passed **13 tests**. The
regression checks the actual guards, source/schema/cancellation prerequisites,
CFB-only report handling and preservation of failure propagation. Independent
review and fresh required CI/CodeQL remain release gates.

After merge, the next already scheduled daily run should refresh profiles and
verify the main capture even if CFB settlement remains degraded. Its overall
failure must remain visible. Do not repeat quote collection to obtain this
checkpoint. Live deployment retains its separate GitHub OAuth dependency.
