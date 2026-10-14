# Durable source for scheduled paper captures

The later [prospective schedule-retention repair](2026-10-05-prospective-schedule-retention.md)
also saves the shared schedule inside each new exclusive attempt. Publishers
and result readers replay that committed copy, so a later shared-file refresh
cannot remove the original schedule evidence. Existing task triggers and
frozen cohorts are unchanged.

The six future local NFL paper tasks used the copied virtualenv with
`python -m sportsbet.quant.kalshi_stat_only_next_capture`. That environment
retained an editable installation pointing into the old Windows Temp
checkout. Its capture and next-evaluation modules omitted the new injury and
weekly-roster receipt and commitment verification; the source-week module's
byte difference was only Windows line endings. Merely changing each task's working
directory therefore did not guarantee execution of the reviewed code.

The tracked standard-library launcher `ops/run_paper_task.py` prepends its own
checkout's `src` directory and verifies the allowed module's exact resolved
path before execution. It permits the free one-shot future capture and its
private commitment publisher, plus the original cohort's offline primary and
after-fee paper score handoffs.
`--inspect-source` prints the local path and SHA-256 without
executing the target. The scheduled tasks now use this launcher with their
original capture arguments. The Python executable, working directory,
triggers, limited interactive principal, power settings and execution limit
are retained; XML definitions are backed up locally before the action change.

Regression verification deliberately put a foreign `sportsbet.py` on
PYTHONPATH and started the launcher outside the repository: it still resolved
the durable local source. An unapproved module was rejected before execution.
The real copied Python environment's inspect and help calls also resolved
the durable source and made no collection request. The combined launcher and
fixed-anchor suite passed five tests.

The separate `kalshi_stat_only_next_publish` companion replays every bounded
capture input, source asset, schedule and context commitment before writing a
private tracked marker. It requires a clean release checkout matching the
remote HEAD, pushes with an exact force-with-lease, preserves that Git object
under the existing protocol's private research ref, then invokes the existing
server-dated PR timeline verifier. Its ignored `remote-anchor.json` is written
only after that verification succeeds. A missing/changed capture, late clock,
dirty checkout, changed remote branch or missing server proof fails; it cannot
collect a replacement quote or outcome.

Six limited interactive publisher tasks are scheduled 25 minutes after their
existing October 8, 10, 17, 24, 31 and November 7 captures, at **17:25 UTC**.
The source capture remains a one-shot attempt with a 15-minute execution
limit. Publishers use the same durable source launcher, request wake and
permit battery operation. A logged-in Windows session is still required.
Focused publisher/launcher, existing capture, source-week and server-proof
tests passed **15/15**; pinned Bandit found no medium-or-higher issue. These
future tasks and their actual pregame proofs still need post-trigger checks.

This repair preserves the frozen model, source-week checks, exclusive attempt
directory, ten-minute window, unsigned free reader and qualification limits.
No future cohort was started or retried. A fresh capture and its independently
verified pregame private commitment remain required before its outcomes can
count toward the prospective evaluation.
