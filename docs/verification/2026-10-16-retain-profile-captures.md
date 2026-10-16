# Retain profile captures when recent inputs are empty

## Observed defect

The profile worker selects a bounded set of signal identities from the past
14 days. When none remained, it published an empty profile snapshot with a new
capture timestamp. This erased the previous metadata even though forecast
archives can still contain older rows.

Archive consumers validate optional profiles against each forecast's capture
time, athlete, team and permitted profile age. An older stored profile can
therefore still be valid for a historical forecast after it leaves the worker's
recent identity window. A synthetic archive replay confirmed that replacing
such a snapshot with an empty one removes its optional presentation metadata.
The observed zero-count worker result alone does not establish that any
particular previously stored profile was usable by the live archive.

## Correction

Publish a profile snapshot only when at least one verified profile was produced.
An empty input retains the previous snapshot and all original timestamps, as a
provider failure already does. The worker's result counts still describe the
current attempt. Existing consumer identity and chronology checks apply to
retained metadata.

## Verification

The focused profile suite passed **8 tests**. New synthetic NFL and NBA cases
verify that empty inputs make no provider request, publish no replacement,
preserve the entire prior snapshot and close the database pool. Existing
successful-refresh and provider-failure cases also pass. Fresh required CI and
CodeQL remain release gates.
