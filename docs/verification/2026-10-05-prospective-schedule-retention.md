# Retain the schedule with each prospective NFL paper cohort

## Reproduced failure

The future one-shot capture already used a durable local schedule file. It
committed that file's SHA-256 but did not retain its bytes inside the cohort.
A shared schedule refresh during source collection changed which schedule
the source-week check, model and control used. After commitment, refreshing
or removing the shared file prevented authenticated replay despite retaining
the other cohort inputs. This lost evidence, rather than making a model edge.

Two synthetic regressions failed before the repair: changing the shared file
during the mocked source stage changed the capture input; replay could not
use an intact original schedule stored beside the pair when its supplied
shared path changed. No real venue, source or result request was made.

## Repair

After writing the exclusive attempt marker and before any network read, the
capture now saves at most 1 MB of the original schedule as cohort-local
`schedule.parquet`. Source-week validation, forecasts, strict prior-20
controls and commitment construction all use this copy. The existing
commitment still binds the same exact schedule SHA-256.

Committed replay prefers the schedule beside the pair. That shared admission
path is used by the publisher, later result collector, evaluator and series
replay. The supplied shared file may change or disappear without changing
the original cohort. A changed, linked, empty, oversized or directory-valued
retained copy fails the existing bounded-input/hash checks; it cannot fall
back to a different shared file. Legacy commitments without a retained copy
still require their original caller-supplied bytes and hash.

Model and evaluation versions, formulas, source chronology, quote policy,
candidate selection, qualification, one-attempt window and result gates are
unchanged. No existing frozen receipt or scheduled task was altered. This
adds a private local file to future captures; it makes no extra API request.

## Verification

- **28 focused tests passed** across future capture, commitment/evaluation,
  publisher, unsigned result collector, series, server-anchor, source-week,
  launcher and context suites.
- A capture retains the original bytes when the shared schedule changes
  during the source stage. Later replay succeeds after shared refresh and
  deletion, without mutating the caller's input mapping.
- A changed retained copy fails before model replay even when the shared
  file has the correct original bytes. A directory in its place also fails.
  A legacy external-only schedule commitment remains replayable and hash
  checked.
- Pinned Bandit passed for both changed modules. The actual scheduled
  launcher resolves the repaired capture in the durable checkout without
  running it. The current shared schedule remains SHA-256
  `4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662`.
- All six future capture tasks remain Ready at their original October 8,
  10, 17, 24, 31 and November 7 **17:00 UTC** triggers. No task was started,
  no quote/result was fetched, and no money or paid credit was used.

The first live verification is October 8 **17:25 UTC (10:25 AM Pacific)**,
after the existing capture and publisher triggers. Verify the attempt's local
schedule matches its committed hash, every source/control/context receipt
replays, and the private pregame push has an independent server timestamp.
A missed or failed attempt remains unavailable. The October 6 original-cohort
result tasks and their existing 7:00–7:20 AM Pacific checkpoint are unchanged.
This retention repair does not establish alpha, a win rate or execution.
