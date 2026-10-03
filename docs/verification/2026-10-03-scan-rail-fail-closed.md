# Consumer scan rail fails visibly on incomplete status

The scan rail previously assumed every HTTP-200 `/api/scans` body was a complete status object. A successful but empty object rendered no league card; `null` could leave it indefinitely saying it was checking. That hides the very pipeline outage that explains an empty pick board.

The private consumer now requires a valid status for every league it is asked to show. Missing leagues, malformed states, timestamps, counts, or budget labels show **Daily scan status unavailable** instead of a blank rail. A league switch discards the prior status while the new read is pending. Abort handling prevents an old request from filling the new rail.

The current production response predates `rolling_release_at` and `rolling_release_passed`. Both absent together are normalized to `null` and `false` as a documented legacy shape; one missing while the other is present is invalid. A read-only request to the deployed endpoint returned HTTP 200 and parsed all three actual stale league statuses after this compatibility adjustment.

Verification: focused scan parser/status tests 21 passed, full frontend suite 290 passed before the final legacy-field adjustment, final focused parser tests 2 passed, TypeScript and targeted lint passed after the adjustment, and the production Next build passed before that small pure-parser adjustment. This changes status presentation only. It does not start a scan, change prices, predictions, qualification, credits, reserves, or spending.
