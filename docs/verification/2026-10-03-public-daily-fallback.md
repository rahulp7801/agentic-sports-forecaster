# Private schedule capacity and daily NFL research receipt

On October 3, 2026, no scheduled `public_daily` run appeared at either
13:17 or 13:47 UTC. [Public run 37127912079](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37127912079)
started at 13:56:45 UTC as `public_monitor`, captured 16 NFL games and 3,408
structured NFL prop markets, and passed readiness and secret scanning. Its
daily-only private pair and raw evidence upload were skipped. The deployed
sanitized market endpoint cannot reconstruct exact asks from that capture.

A first fix changed one existing 13:52 monitor slot into a third daily slot.
A subsequent zero-spend audit showed that the full private hosted schedule
still had **98 public plus 99 paid slots each day**. The representative
successful October 3 public job lasted 82 seconds and a paid job 267 seconds.
GitHub rounds private hosted job execution to whole billable minutes. If all
slots ran for those representative durations, public alone would use 5,880
minutes over 30 days and both would use about 20,730. This is a capacity
scenario, not the account's actual usage. GitHub documents 2,000 included
minutes/month on Free and 3,000 on Pro. The account billing API is not
available to the current token, so the specific allowance balance is unknown.

The **final proposed schedule** instead has 16 public capture attempts/day,
exactly 90 minutes apart: `public_daily` at 12:07 and 13:37 UTC, plus 14
`public_monitor` slots. The paid schedule has a 12:17 UTC all-sport daily run
and 00:19, 16:19 and 20:19 UTC all-sport scan attempts, plus a free NFL
history recovery at 10:29 UTC on Tuesday and Friday. All paid scans keep the
existing 20 daily and 450 rolling credit limits, quote cadence, pregame
reserve, source checks and qualification thresholds. This plan does not add
provider requests or paid capabilities. It removes theoretical duplicate
hosted jobs; GitHub may still delay or drop a scheduled run.

At the representative two public and five paid billable minutes per job, the
new regular 30-day schedule would use about 1,560 minutes, plus roughly 45
minutes for Tuesday/Friday NFL recovery. CI and variable job durations use
additional minutes. The user's $0 stop-usage budget remains the hard
spending guard. This estimate is **not** proof the current billing block is
resolved or that the dashboard will stay fresh 24/7. With 90-minute slots,
any delay can cross the dashboard's existing 90-minute freshness gate, and
those periods must remain visibly stale with no falsely qualified picks.

At 15:28 UTC on October 3, after the live NFL market exceeded 90 minutes old
and no newer scheduled run existed, one free `public_monitor` recovery
[run 37133354666](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37133354666)
failed **before any job step**. GitHub's check annotation cited either recent
payment failures or a spending limit that must be increased. No provider call
or charge occurred. Do not increase the $0 limit or repeatedly dispatch jobs.
A dedicated, secure self-hosted runner is a possible zero-GitHub-minutes path,
but none is registered, and the existing workflow targets GitHub-hosted Linux.

Verification before merge: parse both workflow YAML files; expand cron minutes,
hours, and weekdays; assert 16 distinct evenly spaced public slots, four
normal paid opportunities/day, and Tuesday/Friday-only history recovery.
The focused workflow contract test checks the 90-minute public spacing.
Observe the first real scheduled run after deployment for the correct
operation, complete public quote, retained raw daily evidence/private pair,
and visible stale status when delayed. No October 3 raw ask or forward markout
is invented from the missed capture.
