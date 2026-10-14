# Forward NFL primary correction history

## Failure and repair

Unchanged NFL refreshes already preserve the original source observation in the
existing upsert writer. A genuine correction previously replaced the only
primary row exposed to passing/rushing forecast cards. An older source cutoff
could then lose its form evidence or see a corrected value with a reused early
timestamp.

Migration `0045_nfl_core_history_revisions` retains the replaced, source-backed
primary row in `public.nfl_primary_revisions`. Its fixed trigger leaves every
incoming live stat and `source_observed_at` unchanged. It skips bundle-only
refreshes and derived opponent/home enrichment. Legacy rows without valid
provenance are not turned into source-backed history.

The existing restricted core view now exposes the current and archived versions.
For a corrected row, the card's availability is the later of its source receipt
and its latest database replacement timestamp. Each archived version retains its
previous availability. This separate display chronology prevents a correction
submitted with an old observation time from rewriting an older card. The exact
athlete API selects the latest eligible version per game before its existing
limit, preserving both bound date/source cutoffs and server-side row-hash checks.
Receiving supplements remain on their existing reconciled path.

The archive is owner-only and RLS-enabled. A SECURITY DEFINER trigger with
`search_path=pg_catalog` and fully qualified archive references writes it.
Browser, reader and worker roles receive no direct archive, sequence or trigger
function privileges. Worker updates still succeed through the trigger; only the
restricted dashboard view supplies consumer history. Access provisioning also
closes direct archive grants in either deployment order. A populated archive
blocks destructive downgrade; ingestion and archive locks close the concurrent
correction race before that check. Empty disposable schemas can still round-trip.

## Verification

- Full disposable PostgreSQL migration suite: **12 passed**, including browser
  default grants and roles present before migrations. Empty-schema downgrade and
  upgrade completed using the final quoted-identifier implementation.
- Correction/access/ingestion suite: **11 passed** (five existing SQLAlchemy
  reflection warnings); the retained local output is
  `.local/nfl-revisions-history-tests.txt`. It covers two corrections with the
  original timestamp, exact source hashes, stable earlier/middle cutoffs, one
  displayed row per game, unchanged live timestamps, legacy provenance,
  authenticated worker updates, denied direct access, grant repair, populated
  downgrade refusal, the real upsert writer and mocked NFL season downloads.
- Complete frontend: **329 passed**; TypeScript, changed-file lint and production
  Webpack build passed. Bound SQL selects a version before limiting game count.
- Offline cached Bandit **1.9.4** passed for the changed Python/migration code.
  The staged redacted Gitleaks check passed before retaining this increment.

## Scope and release status

This preserves future corrections after the migration is deployed. It cannot
recover primary rows already overwritten, version the schedule itself or prove
that every historical model input can be reconstructed. No live model query,
frozen evaluator, probability, qualification threshold, candidate set or API
collection limit changes. No data collection, purchase or bet is performed.

The code remains in private PR #345. GitHub's account gate and unavailable
required private CodeQL checks still block hosted CI and protected deployment.
This migration has only run against disposable local PostgreSQL.

The next prospective checkpoints remain the existing October 5 22:58/23:00 UTC
fee/quote tasks and 23:05 UTC private anchor. The October 6 result collection and
primary/net paper scoring run at 14:00/14:15/14:20 UTC (7:00/7:15/7:20 AM Pacific).
Do not duplicate those requests or read outcomes early. A 75% win rate and a
profitable edge remain unproved; retained, paired prospective evidence still
controls those conclusions.
