# Consume profile identities before unrelated waits

## Demonstrated timing conflict

The profile reader accepts market identities at most five minutes old. The
workflow previously called it after the daily graph and CFB settlement finished.

Saved public run receipts show the conflict:

| Run | NFL market capture (UTC) | Producer completion (UTC) | Profile step start (UTC) |
| --- | --- | --- | --- |
| 39045040197 | October 17, 15:27:27.190298 | 15:40:28.247613 | 15:42:45 |
| 39050248837 | October 17, 16:38:43.782571 | 16:43:01.626687 | 16:43:46 |

These are original recorded clocks, not a newly observed failure on the profile
release. In the first run, moving the workflow step ahead of CFB would still leave
identities over twelve minutes old. Another graph node also cannot avoid the
graph's shared superstep barrier with histories.

## Change

For public daily collection, publish each sport's current and upcoming slate
before older schedule catchup. Consume its saved identity snapshots inside the
market coroutine as soon as that sport's market and slate are ready. Keep the
existing research receipt before profile work. Isolate profile failures from
market receipts, preserve original capture clocks and check the database capture
identities against this producer's receipts.

Readiness belongs to each graph invocation, with a bounded wait and release on
schedule failure. Profile diagnostics join the report and its health validation;
failed or degraded profile processing cannot become an observed daily result.
Monitor mode requests no profiles. Remove the late workflow roster call to avoid
duplicate collection.

The public daily catchup-offset database lookup runs in a thread so it cannot
block the early profile coroutine. Nonpublic collection and settlement order stay
the same. Readiness timeout preserves a rejected input state and cannot trigger
another market request.

The five-minute market and fifteen-minute slate limits remain unchanged. Cached
or late inputs can still be rejected. The change adds no quote requests, paid
pipeline activation, new cron slots, forecast tuning or qualification changes.

## Evidence checkpoint

Inspect the next ordinary `public_daily` run after merge for exact head, original
market/slate capture times and profile input/result counts. A successful local
test does not establish live profile coverage, a qualified pick or an edge.
The frontend deployment retains its separate production authentication gate.

## Local verification

**310 relevant tests passed** across daily orchestration/CLI, profiles, exact
identity joins, report validation, workflow configuration, availability,
cross-venue contracts and market collection. The timing regression blocks history
and catchup-offset work until both sports have refreshed profiles, using the real
graph scheduler. Additional cases cover cancellation, failed schedules, timeout,
reused/concurrent graphs, failed market/profile isolation, exact capture mismatch
and stale market reuse without another quote or roster request. All sources and
database responses are fixtures; no live collection or frozen source edit was
performed for this verification.
