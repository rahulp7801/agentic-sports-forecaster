# Diagnose rejected profiles and fatal public-pipeline failures

## Newly observed scheduled evidence

Both natural runs on `c2c94fc1d5ac10fe41ba2eb452f37830411bc73d` retained the original cron and actual selection:

| Run | Original cron | Created at UTC | Actual operation |
| --- | --- | --- | --- |
| `39142000274` | `7 12 * * *` | `2026-10-18T15:46:34Z` | `public_daily` |
| `39146778357` | `37 13 * * *` | `2026-10-18T16:49:44Z` | `public_daily` |

The receipts establish delayed daily runs. Creation time alone would not have identified their triggering slots.

The first producer reported 95 NFL profiles, 68 unavailable identities and 163 public identities across 11 selected events. NBA public inputs were rejected, with zero selected identities. The aggregate report did not retain the failed validation check. Neither staleness, partial game sampling nor a particular identity defect can be established from that output.

Its original NFL market capture was `2026-10-18T15:47:09.134022+00:00`; NBA was `2026-10-18T15:47:36.934529+00:00`. The exact report validator accepted four receipts, database publication verified four, and the separate CFB slate verified one. A degraded producer exit of 2 did not skip these checks. Production readiness then failed on the existing missing `id="waitlist"` landing-page marker.

NFL settlement retained 26 final-stat gaps; CFB retained 19. Settlement totals in these reports count attempts/revalidations and do not establish new wins or a prospective edge. Profile counts are producer-reported metadata, not qualified picks or independent byte verification of the profile snapshot.

The second run emitted no final main report. It logged `Daily pipeline unavailable (OperationalError)`, a failed CFB receipt verification, and `Free CFB settlement unavailable (OperationalError)`. The underlying SQLSTATE and failing main-pipeline stage were absent. Successful schema verification earlier in that run does not establish later database availability, and the receipt failure cannot be classified as a mismatch rather than a connection/read failure.

## Bounded diagnostic change

Rejected profile inputs retain only fixed validation stage/reason pairs. The public report validator accepts the explicit diagnostic contract and rejects arbitrary fields or values. Existing source, hash, chronology, capture-pin, identity and freshness checks still determine acceptance.

Fatal pipeline and CFB operations, and publication receipt verification, emit bounded operation/stage/error-type diagnostics with a syntactically valid SQLSTATE when available. Exception messages, SQL, parameters, DSNs, provider payloads, full tracebacks and player identities are excluded. Existing failure exits remain failures; the change neither retries an operation nor converts incomplete evidence into a successful report.

No schedules, collection requests, API caps, staged reserve, source clocks, frozen artifacts, forecast/evaluation versions, qualification thresholds or owner-only access settings change. This is an observability fix; it does not establish recovery of the rejected NBA inputs or the later database failures.

## Verification

The focused suite passed 285 tests in the existing lockfile environment. It covers profile and cross-venue validation, strict public-report fields, actual async graph failures, CLI exits, CFB stage boundaries, exact receipt checks, diagnostic redaction and workflow collection gates. Database/provider failures use injected fixtures; these tests do not establish current hosted database health. Independent code and evidence reviews found no remaining must-fix issue. Required CI, CodeQL and postmerge production checks still apply.

## Next evidence checkpoint

Inspect the next naturally scheduled run on the merged diagnostic release. Retain its original cron and selected operation, exact successful source clocks, profile reason codes or fixed fatal-stage/SQLSTATE diagnostic, and each actual publication verification result. Do not recollect quotes or infer a successful capture from a diagnostic clock.

The contained public landing release remains subject to its protected checks and the recorded free-deployment-quota cooldown. The separate owner-authenticated release also requires the missing GitHub OAuth settings. Original frozen evidence and admission requirements remain unchanged; complete-cohort outcome review still requires authenticated final results and its original admission checks.
