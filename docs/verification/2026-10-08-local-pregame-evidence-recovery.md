# Local recovery for the next pregame captures

## Scope and owner instruction

The original one-shot collector retains raw source/model/quote/decision evidence
under ignored `.local/next-nfl-stat-only-<stamp>` directories. Its existing private
GitHub markers preserve hashes and server push chronology, rather than those
raw files. Replaying the evaluation requires both the retained bytes and the
preserved source commit.

Automatic approval review rejected a proposed recurring raw-evidence uploader
because the payload and cadence required explicit authorization. The uploader
was not written. The owner then selected **“Keep future evidence local.”**
The implemented recovery module is consequently local-only: no upload, draft
creation, provider request, credential read, paid storage or publication path.
The previously authorized October 3–4 private recovery draft is unchanged.
Existing hash-only pregame markers and code pushes remain unchanged.

## Implemented local package

`kalshi_paper_local_recovery.py` runs after the publisher has verified the
primary, teammate and role markers in the same server-published preserved commit
and saved the original `remote-anchor.json`. It does not change that proof or
its return contract.

The allowlist contains only the exact 15 original capture-root files, seven
source files and the authenticated context inventory (one unavailable receipt
or the five observed receipt/metadata/Parquet files). Unexpected `.env`, logs,
directories, symlinks, Windows junctions, path escapes, missing files and size
overflows reject the package. Files are bounded individually to 30 MB and in
total to 100 MB; the resulting archive is bounded to 50 MB.

The bytes actually packaged are checked against the original pregame commitment,
the replayed model and both study receipts, each source-manifest size/hash, and
the context receipt/asset/release-metadata hashes. This closes the interval
between source replay and packaging: changed source or context bytes cannot
quietly enter an apparently verified recovery archive.

The existing installed Windows Gitleaks 8.30.1 binary is pinned by its observed
SHA-256 before execution. It scans the allowlisted local staging tree with
redaction. Scanner absence, mismatch or rejection leaves a recovery failure;
there is no fallback to an unscanned success.

An exclusive ZIP and per-file recovery manifest are written under
`.local/paper-local-recovery-<stamp>/`. Every entry is read back against its
size and SHA-256, with bounded decoded size, unique names and safe capture-relative
paths. Verification parses the exact in-memory bytes whose archive hash was
checked. Original pregame/source/quote/server clocks remain inside unchanged
receipts; the new manifest labels its actual recovery time separately.

`package.json` explicitly reports `status: local_verified` and
`remote_backed_up: false`. Existing archives are not overwritten. Backup failure
records a bounded generic local status outside the original capture directory
and emits a generic publisher warning, while preserving the original verified
anchor. If the disk is also full/unwritable when writing that failure status,
the handler still returns failure without propagating a new publisher exception.
Raw scanner findings and exception messages are not logged.

This is local replay/recovery preparation, **not an off-PC backup**. It does not
protect against losing the entire PC/disk, and it supplies no new outcomes,
prospective cases or evidence of an edge. No frozen model/evaluation source,
qualification threshold, staged reserve or provider-credit limit changed.

## Verification and next checkpoint

New tests cover exact source/context inventories, original byte preservation,
changed forecast/source/context/study rejection after replay, mismatched proof,
scanner pin/rejection/redaction, bounds, archive corruption/path traversal,
exclusive outputs, full-disk failure isolation and publisher sequencing after
all three verified markers. The common prospective capture, role weighting,
teammate and source-safe launcher tests are included in focused verification.
The completed focused suite passes **155 tests** (48.43 seconds). Its sole
warning is the unused `asyncio_mode` setting with automatic plugins disabled.
Cached Bandit and staged redacted Gitleaks passed. The actual pinned scanner
also passed on the retained allowlisted October 3–4 staging evidence. That
compatibility check made no upload or new collection. All six original frozen
recent-gap/evaluator sources remain unchanged.

At **October 8 17:25 UTC / 10:25 AM Pacific**, inspect both scheduled exits,
the original capture receipts, all three preserved pregame markers and the new
local `package.json` or explicit recovery failure status. A marker alone does
not prove a recoverable archive. At October 10 17:25 UTC, check the fresh Saturday
capture and Sunday context coverage. No missed pregame capture can be backfilled;
the original full-cohort result gate still determines when scoring may start.

Owner OAuth settings, the protected waitlist environment, the account CI gate
and required private CodeQL remain release blockers; this local change bypasses
none of them. No production deployment or market advantage is claimed.

## Hosted workflow retention follow-up

An audit of the pending release found three remaining raw artifact upload paths:
the paid worker's staged public evidence, the public worker's staged public
evidence, and its private NFL source/model/market pair. The latter still uploaded
automatically even with the manual retention input defaulted off; scheduled
daily public evidence also uploaded automatically. These conflicted with the
owner's subsequent local-only raw recovery preference.

Both collector workflows now stage and secret-scan their raw files locally but
have no artifact packaging/upload or release-upload step. The manual raw-retention
input and unused Actions-read permission are removed. An explicit run summary
states that hosted runner storage is ephemeral and no durable raw backup is
created. The owner's durable local paper captures, verified local packages and
hash-only remote chronology anchors retain their existing paths. Normal private
application database snapshots and aggregate evaluation checkpoints retain
their existing purpose; this change governs raw-file artifact/recovery copies.
The original one-time private recovery draft is unchanged.

An independent comparison against the prior release verifies that schedules,
job/production guards, collection inputs, credit caps and every operation before
raw retention are unchanged. All 27 Bash run steps in the two resulting workflows
pass syntax checks without executing collection or uploads. No provider request,
new quote capture, task-setting change, storage purchase or production mutation
was used for this audit.

The first retention regression run reproduced all three raw-upload violations
and also exposed four stale workflow tests for the old public verification flow.
Those tests now verify restricted private snapshot receipts, the contained
deployment/owner-auth transition, conditional unchanged-release checks and
interruption recovery. Credential assertions bind the snapshot verifier only
to its restricted database reader and keep owner session/provider/deployment
tokens outside public verification. A further obsolete upload expectation in
the private-evaluation test is replaced with local-only retention and no report
dumping. Protected production checks and runtime release logic are unchanged.

The focused workflow/packaging/settlement/storage suite passes **24 tests**.
The protected deployment/containment/database-preflight script suite passes
**62 tests** with zero failures, skips or cancellations. The frozen quant
implementations and prospective study populations are not modified. This
retention policy remains in private review until the protected release executes.

The final full backend gate passes **2,453 tests**, with **100 skips** (including
explicit disposable-database requirements) and seven existing NBA mock-ingestion
warnings, in 103.95 seconds. Its initial broad run also exposed two subprocess
imports using system Python without the checkout/dependency paths; the final
isolated localhost run explicitly passes those absolute paths through
`PYTHONPATH`, and both subprocess regressions pass. No production database was
used. This local result does not establish hosted CI or production activation.
