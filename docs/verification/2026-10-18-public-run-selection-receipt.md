# Record the original public-run selection

## Observed gap

Scheduled run `39126192900` was created at `2026-10-18T12:10:28Z` on commit `21aac9e82a81fec43cbb77e8c4d5c4355de1d7c5`. Its producer reported `public_monitor`; profiles, histories and settlements were not requested. The report and database publication receipts passed, while the deployed landing page still lacked its waitlist marker.

The original triggering cron was not retained in the saved output. Creation time cannot identify whether this was a delayed earlier monitor slot. It does not establish a daily-mode selection bug, and the run does not verify the pending daily profile-timing fix.

## Change

Before dependency installation, configuration checks or collection, the existing public workflow records a small, fixed-shape `public_run_selection` receipt. It contains the event name, original cron (null for manual dispatch), actual selected operation and sport, source commit, run ID and attempt.

The helper validates bounded, allowlisted metadata and reads only the seven named environment values it needs. It never dumps the full environment or event payload, loads credentials, fetches data, writes files or uploads an artifact. Invalid metadata produces a fixed error without echoing its contents.

This records the selected mode without deriving a replacement from the cron. If a valid cron and mode disagree, their actual values remain visible. The workflow's existing operation/sport expressions, sixteen slots, two daily slots, concurrency, API budgets, reserve and collection calls are unchanged.

## Evidence limits and next checkpoint

The receipt is workflow attribution. It is not a source capture, signed timing proof, authenticated outcome, prospective admission or evidence of an edge. It adds no capture timestamp and does not backfill older runs or change frozen receipts.

The helper passed 10 behavioral tests, including actual CLI output and secret-omission cases. Workflow integration passed 15 tests, including the unchanged scheduled slots, selection expressions, credential scopes and collection ordering. Independent review found no remaining must-fix issue. Real required CI and CodeQL gates still apply before merge.

After the next natural run, retain its original cron and selected operation alongside the producer report. For an actual `public_daily` run, separately inspect the original market/slate clocks, profile input/result status and publication receipts. A delayed or dropped scheduled attempt must not trigger duplicate quote collection merely to obtain a trace.

Production UI deployment remains subject to the existing protected release gates and the separately recorded Vercel free-quota cooldown. This workflow-only diagnostic does not retry deployment or change live access.
