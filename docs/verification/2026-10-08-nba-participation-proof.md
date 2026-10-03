# NBA participation proof — October 8, 2026

## Concrete gap

The frozen NBA result commitment covers player ID, game ID/date, team, points,
rebounds and assists. It does not cover minutes or player name. The existing
official upsert already moves its observation when any supplied field changes;
that protection remains. However, overwriting a minutes row leaves no separate
commitment or prior minutes version for an earlier teammate comparison. A valid
core result hash alone cannot prove the displayed participation value.

NFL touchdowns were also inspected. They are already excluded from automatic
core settlement and the verified core-history response. No frozen stat hash,
model, qualification threshold or research implementation was changed.

## Forward repair

Pending migration `0048_nba_participation_versions` adds append-only player/game
participation versions. Actual existing official/ESPN provider inputs commit
player name/ID, game/date, season, team and minutes at PostgreSQL's one-decimal
storage precision. The official source has a separate scope-bound normalized
minutes batch; ESPN retains its existing raw-response hash. These are distinct
from the frozen core result hashes. Existing database rows receive no backfill.

Both source writers append accepted minutes in the same transaction as their
normal stat write. Official NBA priority over ESPN remains. Exact retries and
batch-only changes retain the original version and receipt; corrections and
reversions receive new versions. Changed older observations abort both writes.
Omissions from a nonempty complete official season produce an unknown-minutes
version, never an invented zero. Existing ESPN participant-removal reconciliation
still fails closed. An empty official response does not declare a complete
historical withdrawal.

The descriptive reader chooses each complete eligible player/game version
before filtering name or team, verifies its normalized commitment, and binds a
unique participant identity. Only proved positive minutes establish tenure;
only proved zero minutes count as absent. Missing, null or invalid participation
is unknown. Subject points/rebounds/assists/PRA replay their original core
commitments. Uncommitted auxiliary NBA props cannot use these comparisons.
Source observations and database acceptance clocks must precede the forecast.

Private forecasts retain the selected source rows and compact identity version
references. The consumer projection publishes only bounded aggregate v3
comparisons and strips rows/references/cutoffs. Older NBA v2 comparisons are
withheld while preserving current injury reports and model probabilities. NFL
v2 behavior remains unchanged. No old forecast or probability is rewritten.

Database acceptance clocks are transaction timestamps, not exact commit
visibility receipts. The retained original selections support auditing what
was actually read; clock-only reconstruction must not be advertised as proof
of exact historical visibility. Missing legacy participation is not repaired
retrospectively from current database minutes.

## Security boundary

Browser and dashboard roles cannot read this table or its sequence/function.
The worker can select and append only source/value columns. It cannot set
version IDs or receipt clocks, update, delete or truncate history. A fixed
owner-executed trigger serializes player/game changes and owns the receipt.
Populated downgrade refuses to erase retained proof. Both role/migration
provisioning orders are covered.

Final permission review reproduced another concrete gap: PostgreSQL column
grants survive a table-level revoke. Private-table repair now explicitly clears
column grants before restoring permitted worker columns. Actual tests grant
browser minute reads and worker receipt/ID inserts, then verify repair removes
them while normal append operations still work. The tracking archive boundary
is rechecked as well. No production permission or schema change ran.

## Verification

- Full backend suite: **2,507 passed**, 128 environment/database skips and seven
  existing mocked NBA/pandas warnings. Final source-proof cases: 64 passed.
- Full frontend suite: **335 passed**. TypeScript and changed-file lint passed.
  Tests preserve current injury reports/probabilities and strip private proof.
- Full migration-chain gate: **12 passed**.
- PostgreSQL release gate: **148 passed**, 29 existing SQLAlchemy reflection
  warnings. It covers actual official/fallback writers, source priority, numeric
  precision, corrected/reverted participation, pinned cutoffs, missing proof,
  provider omissions, same-name/team corrections, rollback, role order and the
  populated-downgrade guard.
- The last column-grant repair additionally passed both affected NBA/tracking
  PostgreSQL permission tests. Cached Bandit passed without downloads.
- All database tests used the cached PostgreSQL 16 image in a task-owned
  loopback-only container; no production data/provider request was used.

The waitlist provisioner now requires the exact reviewed `0048` head; existing
fixed waitlist function attestation and protected release gates remain.
CI explicitly includes the new PostgreSQL tests. These local results do not
replace required hosted checks or activate the pending release.

## Privacy and next checkpoint

Repository metadata/collaborators were rechecked: private, only owner
`rahulp7801`, immutable account ID `76501505`, zero invitations. PR #345 remains
one consolidated private release commit. Raw future evidence stays **local**,
as the user requested. No recurring backup upload/draft, new quote request,
purchase, card use, paid storage, bet or extra scheduled task was added. The
20/day, 450 rolling and staged reserve constraints are unchanged; PR #194 is
not merged. Both original pregame research refs remain unchanged.

The original October 8 capture/publisher tasks are Ready. Capture is
**17:00 UTC / 10:00 Pacific**, publisher **17:25 UTC / 10:25 Pacific**. Inspect
their actual exit codes, original matching prices/source chronology, all three
studies' preserved pregame anchor and the local recovery package at that
checkpoint. Do not reconstruct a missed pregame capture after kickoff.

Required exact-head CI/private CodeQL, owner OAuth configuration and protected
waitlist verification still precede production activation. Existing public
containment remains. This repair makes context auditable; a profitable market
edge and a 75% individual pick win rate remain unproved.
