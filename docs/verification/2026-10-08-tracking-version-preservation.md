# Tracking version preservation — October 8, 2026

## Concrete failure and repair

The tracking writer previously replaced every row in a season/stat partition.
That handles provider removals, but destroys the source version used by an older
forecast. Keeping individual old rows alongside new ones would instead mix
source files and could resurrect a removed player or week during replay.

Pending migration `0047_ngs_partition_versions` retains complete partitions.
Its owner-executed, fixed replacement function serializes writers, archives the
whole prior partition and installs the replacement atomically. Exact retries
preserve IDs and original observation times. Older observations, duplicates,
unknown fields, contradictory provenance and invalid stored values abort the
transaction. A digest commits the sorted retained row hashes for each version.

The worker receives read access through restricted catalog/history views and
permission to execute that function. Direct tracking mutations and direct
archive/catalog table access are denied. Dashboard and browser roles receive
neither the views nor the function. Access repair handles actual attached
sequences, including tables without sequences, and closes accidental browser
sequence grants as well as table grants. Both provisioning orders are tested.

The reader selects one eligible whole partition per season/stat before choosing
the latest eight prior weeks. It still requires one matching source file across
the sample and replays each normalized row commitment. A private forecast keeps
the exact partition IDs, set hashes and catalog metadata for pinned replay.
Provider removals cannot fall back to an older partition. The consumer
projection strips these private references and raw source rows.

## Timing limits

For live reads without an explicit cutoff, the reader obtains the database
clock. Local tests reproduced host/database skew that otherwise briefly hid an
accepted version. An explicit cutoff remains authoritative when supplied.

Catalog `recorded_at` is a database acceptance clock inside a transaction, not
the exact commit-visibility timestamp. Pinned version references preserve what
the original query actually selected; clock-only replay must not be advertised
as proof of exact commit visibility. Initial legacy partitions keep their
original metrics, hashes and individual observations. Their catalog clock uses
the latest retained source observation, the available legacy lower bound; this
does not reconstruct previously overwritten partitions or historical commits.

The full PostgreSQL gate also reproduced an existing defect in the pending,
undeployed `0045_nfl_core_history_revisions` trigger: a replacement timestamp
could precede its new source receipt when the host clock was ahead. Its forward
transition now follows both receipts and the previous version monotonically.
Tests cover an ahead source clock and a later backdated correction. These
transition clocks are conservative availability bounds, not commit receipts.

The waitlist provisioner now requires the exact reviewed `0047` schema head;
its fixed `0046` waitlist function attestation remains unchanged. CI explicitly
includes the new tracking tests and the pending NFL archive tests.

## Verification and release boundary

- Full backend suite: 2,481 passed, 117 database-dependent tests skipped;
  seven existing mocked NBA/pandas warnings. The last added clock regression is
  executed in the separate PostgreSQL gate.
- Full frontend suite: 335 passed, including private reference stripping.
- Cached Bandit 1.9.4 scan of changed production code and both migrations:
  passed, without downloads.
- Final full-chain migration gate: 12 passed, including upgrade/downgrade and
  existing-role/default-grant checks.
- Final PostgreSQL release gate: 138 passed, including whole-partition replay,
  both permissions provisioning orders, real writer precision, provider
  removals, the clock regressions and complete-chain waitlist provisioning.
  Ten existing SQLAlchemy `upsert` warnings remain.

All database verification uses task-owned disposable PostgreSQL 16 on
`127.0.0.1:55487`, with the existing cached image. No production schema or
tracking partition was changed and no new provider/market quote was collected.
No purchases, paid infrastructure, credits, subscriptions or bets were used.

Repository access was rechecked: private, owner account ID `76501505` only,
zero outstanding invitations. PR #345 remains the consolidated reviewable
release; production changes require its existing protected CI/deployment gates.
The prior exact-head CI run failed before runner steps because GitHub refused
job startup under the account payment/spending gate. No protection is bypassed.

Future recurring raw evidence backups remain local, per the user's choice.
No draft backup or raw source package is uploaded by this work. Existing normal
private application history and hash-only pregame anchors retain their roles.
The frozen research source and original October 4 cohorts are unchanged; this
repair supplies reproducible context, not evidence of a profitable edge or a
75% individual pick win rate.

## Next evidence checkpoint

The already scheduled October 8 capture is at **17:00 UTC / 10:00 Pacific**;
the hash-anchor publisher is at **17:25 UTC / 10:25 Pacific**. After both finish,
verify the original capture's source observations, slate/week, matching prices
and local recovery package; all three independent studies must share the same
preserved anchor commit and a verified push before kickoff. Record an actual
failure if capture or publication fails. Do not collect redundant quotes or
reconstruct a missed pregame after results. Subsequent frozen captures remain
October 10, 17, 24, 31 and November 7 on the existing schedule.
