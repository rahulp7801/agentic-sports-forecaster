# Current production history maintenance

## Read-only starting checkpoint

An owner-authorized read of the existing production worker database used
hostname-verifying TLS, the committed Supabase CA, disabled prepared statements
for the transaction pooler and a read-only transaction. It made no mutations or
provider requests. The deployed schema is `0039_prediction_record_receipts`;
the pending NFL versioned/core history views and migration 0045 are not deployed.

| Sport | Visible rows before maintenance | Latest visible game date | Last completed refresh |
| --- | ---: | --- | --- |
| CFB | 48,345 | 2026-10-02 | 2026-10-02 18:25:28 UTC |
| NFL | 57,827 | 2026-10-01 | 2026-10-03 14:49:20 UTC |
| NBA | 52,957 | 2026-04-12 | 2026-10-02 18:43:54 UTC |

These are database coverage observations, not accepted picks or evidence of an
edge. A successful historical refresh does not establish a successful current
market scan, available injury context or complete prospective evaluation.

## Verified CFB update

The maintenance used the already released worker source at
`403e24106f58707188f94963fe3603612f455b58`, rather than deploying the pending
model/auth branch. The two free sportsdataverse/ESPN assets were downloaded once,
retained locally, normalized with the released parser, replayed and secret-scanned.
The completed-game schedule had no future inputs: its latest game started at
2026-10-08 00:04 UTC, before the source plan observed at 09:24:40 UTC.

The prepared plan contained 8,968 current-season player-game rows, including
1,286 missing keys and zero corrections to the 7,682 existing rows. The parser
skipped 370 unattributed team aggregates. The deployed CFB revision trigger was
required before applying the released updater; its unchanged-row behavior
preserves previous observations even when the source bundle hash changes.

The operation finished at **2026-10-08 09:32:35 UTC**. An independent read verified
8,968 current-season rows, 1,286 additions, zero corrections and preservation of
every old row hash and original observation time. The dashboard view now has
**49,631 CFB rows through October 8**.

The existing released snapshot writer then published and read back one truthful
`refresh:cfb` receipt, with the released provider/season coverage shape and an
explicit `released_current_season_history_only` maintenance description. It
does not claim a new quote scan, backfill, model release or end-to-end workflow.

The raw assets, full prior-row metadata, source hashes, normalization plan,
verified result and dashboard readback remain under ignored
`.local/current-cfb-history-20261008/`. Applying the retained bytes and publishing
the receipt made no further source downloads, odds requests or raw uploads.

## Verified NFL append-only update

The released NFL season refresher rewrites existing source observation times.
Migration 0045 and the reviewed preserve-on-unchanged updater remain pending.
Running that full legacy refresher would therefore damage the historical
chronology the prospective studies depend on.

A separate local maintenance plan instead replays the exact released NFL
normalizer against two bounded free nflverse Parquet assets. It requires completed
regular-season game evidence, matching existing parent schedule identities,
unambiguous club/opponent mapping and matching normalized stat commitments.
It contains **1,042 missing Week 4 player rows through October 5**, with **zero
existing corrections**, against 3,403 current-season production rows. The plan
and its secret scan made no database writes or odds requests.

The transaction inserts only those missing primary keys with
`ON CONFLICT DO NOTHING`. It compares every full existing row under a table
write lock, verifies each inserted stat hash, provider, batch hash, observation
time and matchup, and rolls back on any conflict or mismatch. It performs no
schedule updates, existing-row corrections, source download, schema migration
or model/auth deployment. At **2026-10-08 09:47:23 UTC**, a separate post-commit
read verified **4,445 current-season rows**, all **1,042 additions**, every new
source commitment and preservation of all **3,403 existing full rows**, including
their original observations and IDs. The dashboard view now contains **58,869
NFL rows through October 5**. No existing correction was applied or needed.

The raw sources, full baseline and normalized plan are local-only under ignored
`.local/current-nfl-append-history-20261008/`. This append operation does not claim
to refresh NFL snap counts, Next Gen Stats, injury/availability context or the
entire `refresh:nfl` workflow. Existing corrections must wait for the protected
history-preservation release.

The released snapshot writer published and read back a separate sanitized
`maintenance:nfl:player_stats` receipt after another full baseline/new-source
verification. Its scope is explicitly `player_stats`, and `full_refresh` is
false. The older `refresh:nfl` payload was independently confirmed unchanged.
A final read confirmed the CFB/NFL counts and dates above and unchanged NBA
coverage. No live odds scan or optional context update was invoked.

Verification exercised the real production transaction and post-commit reads,
not a synthetic claim of refreshed history. The NFL plan's 4,445 normalized
records replayed against its exact retained source bytes before insertion.
Both local raw maintenance directories passed redacted Gitleaks scans. No
application runtime source changed in this documentation increment; the prior
full local release checks (2,453 backend passes, 335 frontend passes, TypeScript,
lint and production build) retain their existing scope. Hosted CI remains a
separate requirement.

## Release and prospective checkpoint

These authorized data maintenance operations preserve model/evaluator versions,
qualification thresholds, the staged pregame reserve and the 20-credit daily /
450-credit rolling odds limits. They make no purchases, bets, orders, public
publication or new raw-evidence remote backup. The owner's instruction to keep
future raw evidence local remains in effect; ordinary private application data
and sanitized aggregate verification notes retain their existing purpose.

The consumer release still requires protected hosted CI, required private CodeQL,
owner OAuth configuration, waitlist provisioning and production verification.
Its reviewed local checks do not replace those gates. The existing containment
firewall stays in place until the owner-auth release is verified. PR #194 remains
unapproved and unmerged.

At **October 8 17:25 UTC / 10:25 AM Pacific**, inspect the actual exits of the
17:00 capture and 17:25 publisher, original source/quote chronology, all three
prospective study receipts and hash markers in the same server-published preserved
commit, and the local recovery package or explicit failure status. The owner's
PC must be on and logged in. No missed pregame capture can be backfilled, and no
new quote request should duplicate those scheduled observations. A sizeable
edge or 75% individual win rate remains unproved.
