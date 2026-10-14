# NFL tracking commitments and current participation

## Authoritative current-context gap and maintenance

After the verified primary-stat update, a read-only production audit confirmed
Week 4 statistics for all 32 clubs but only 91 snap-count rows for two clubs in
one game. Missing snap rows remain unknown participation; they do not prove
absence. Passing/receiving/rushing NGS likewise covered only the Thursday game.

Using released source `403e24106f58707188f94963fe3603612f455b58`, one bounded
free nflverse snap-count asset was downloaded, validated and secret-scanned.
The already retained completed-game schedule was reused without another download.
The plan contained 1,391 missing Week 4 participation rows for 30 team-games,
with no corrections to the existing 4,579 rows.

At **2026-10-08 10:02:02 UTC**, append-only production maintenance completed.
Its transaction compared every prior full row under a write lock, checked exact
completed schedule identities and replayed each new commitment before commit.
Independent readback confirmed all 4,579 old rows and observations unchanged,
all 1,391 new rows, and **1,482 Week 4 rows across 32 teams and 16 games**.
Current-season participation totals 5,970 rows. Explicit recorded zeros retain
their existing unknown-participation semantics.

The released writer published and read back a separate sanitized
`maintenance:nfl:snap_counts` receipt with `full_refresh: false`. Another
baseline/new-row verification preceded that write. The older full NFL refresh
payload was independently confirmed unchanged.

The raw asset, full baseline, normalized plan and readback remain local-only
under ignored `.local/current-nfl-snap-append-20261008/`. No odds request, source
request during apply, correction, schema change or model change occurred.
This updates participation only; it does not claim current injuries, refreshed
NGS, a complete NFL workflow, a newly accepted pick or measured alpha.

## Tracking proof failure and reproduced cause

A separate read-only replay of the released row commitment against the actual
stored 2026 NGS fields found **0/425 matches**: 100 passing, 225 receiving and
100 rushing rows. It exposed no player names, IDs or metric values and made no
provider request or database mutation. This shows that those stored rows cannot
reproduce their saved commitments; it does not by itself establish the cause of
every mismatch or prove malicious alteration.

A new local regression reproduced a concrete cause: the normalizer committed
high-precision floats before PostgreSQL rounded them to the declared NUMERIC
scale. Its saved row digest consequently differed from the actual retained row.
The regression failed before repair. The raw source-file SHA remains a separate
commitment and is never rewritten to mean the rounded row.

The normalizer now quantizes to the declared database scale with decimal
half-away-from-zero rounding before computing the row digest. Values exceeding
NUMERIC precision or SMALLINT counts reject before a write. Coverage explicitly
labels `ngs-db-precision-v2`. This makes the commitment describe the values the
database actually retains; it does not increase their precision or change a
model probability.

Actual read-only PostgreSQL casts of three synthetic normalized fixtures
verified all five passing, five receiving and four rushing numeric columns
against the production schema. All resulting rows reproduced their new digest,
including a negative rushing metric and differing two/three-decimal scales.
These were scalar SELECTs, not fixture inserts or production ingester runs.

The actual pending aggregation SELECT also ran successfully in a read-only
production transaction. Its retained eight-week sample was withheld by the new
proof verifier, consistent with the independently observed commitment failure.
No private rows were published and no stored data changed in this check.

## Consumer source boundary

The pregame tracking query retains its exact prior-week, observation-cutoff,
eight-week limit and single-source-version gates. It now also returns the
bounded retained rows privately for verification. Before publishing an average,
the producer replays every row commitment, matches player/type/provider/source,
checks row observation clocks, reconciles all displayed periods and verifies
the aggregate against those committed metrics.

Missing, contradictory, late or uncommitted rows withhold optional tracking
context. Successful output labels `ngs-row-commitment-v2` and contains only its
existing public averages, sample metadata and provenance. Private retained rows
never enter that result or the browser. The consumer projection requires the
verified marker; older unverified tracking attachments are omitted while their
forecasts, probabilities and eligibility retain their existing meaning.

Tests cover altered metrics/digests, wrong identity/periods, later observations,
missing raw proofs and a forged average despite valid row hashes. Browser checks
cover missing/legacy markers, raw-row stripping and repeated projection without
probability changes. No frozen quantitative evaluator, qualification threshold,
odds quota, staged reserve or prospective study membership changes.

## Verification and remaining work

The final focused backend suite passes **75 tests**; the tracking/consumer
suite passes **49 tests**. Full backend passes **2,461 tests**, with **100 skips**
and seven existing NBA mock-ingestion warnings, in 92.02 seconds. All **335**
frontend tests pass. TypeScript, changed-file lint, the production Webpack build
and cached offline Bandit pass. Additional precision-overflow fixtures reject
before a write; the final 75-case targeted run passes. The final consumer
projection rerun passes all 46 cases, including private raw-row stripping.
The staged secret scan precedes recording the increment. The full backend count above is the completed broad
run before these extra test cases, with the same final runtime implementation.

This repair remains in private review. It has not rewritten, removed or claimed
to repair the 425 existing production tracking rows. The legacy tracking updater
replaces whole source partitions and the consumer requires one matching source
version. An append-only NGS update would create mixed versions, while a legacy
replacement would lose older source-cutoff replay. Tracking version preservation
therefore remains a concrete next task before refreshing that production data.
The new consumer guard withholds unreplayable tracking rather than advertising
its metrics as verified.

Protected CI/account, private CodeQL, OAuth and waitlist activation gates remain.
Privacy containment stays active and PR #194 remains untouched. No purchase,
bet, order, paid quota increase, raw remote backup, production code deployment
or unapproved merge occurred. The next prospective capture checkpoint is still
**October 8 17:25 UTC / 10:25 AM Pacific**, with all three same-commit pregame
markers and a verified local recovery package; no missed capture can be repaired
after kickoff. A 75% win rate or sizeable market edge remains unproved.
