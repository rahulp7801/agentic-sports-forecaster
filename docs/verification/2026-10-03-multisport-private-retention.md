# Private NBA and corrected-CFB prospective report retention

The daily worker already retains old and corrected NFL priced checkpoints. Its existing
12:17 UTC daily run now also evaluates NBA's frozen `nba-cfb-priced-prospective-v1`
cohort and CFB's separate corrected-history `cfb-history-priced-prospective-v1`
cohort. The older CFB v4 cohort remains under the original research protocol and is
not mixed into the corrected model. Each report uses one repeatable-read,
read-only hosted snapshot for its all-forecast and accepted-pick denominators, then
appends aggregate JSON through the restricted `sportsbet_worker` role. The database
stamps its own write time and verifies the JSON digest. No player rows, forecast IDs,
provider credentials, or raw quote sources are published in the report.

The retention code fixes the evaluator and dependency source hashes, rejects nested
player-level identifiers and row arrays, verifies the
existing protocol hash, exact sport, two cohorts, status, aware timestamp, and
`promote=false`, then sets `target_verified=false`. A source change requires a new
protocol/review. These are retention checks as of this release; they do not claim the
new storage code existed at the earlier model cohort cutoffs. The frozen evaluator
itself still requires 50 paired decided games and 100 settled accepted picks from
30 games, with favorable game-cluster intervals for both market skill and
recorded-stake return. No automatic model promotion, 75% claim, or executable
profit claim follows from storing a report.

Migration `0042_multisport_private_reports` adds only the two explicit protocol names
to the existing private append-only table check. Normal role provisioning already
grants the worker reads of the forecast and quote tables used by the scanner.
Role provisioning now also grants private report SELECT/INSERT and sequence use
when a new installation migrates before creating the roles. It restores only
the report table's worker RLS policies, denies browser roles on that table and
sequence, and grants no report UPDATE, DELETE, or TRUNCATE.

The daily step has no API key, is bounded to five minutes, attempts NBA and CFB
independently, and makes no provider request.
An audit failure logs only its sport and exception type, still attempts the other
sport, then fails the step. It uses the existing daily job, $0 GitHub Actions
budget, 20 daily/450 rolling Odds API limits, staged reserve, and normal
schema-head check.
It does not add a scheduled run. Manual `--sport nba`, `--sport cfb`, or `--sport all`
invocation requires an existing restricted hosted database URL; it writes private
reports and must not be used as an uncontrolled retry loop.

Before production use, apply the reviewed schema migration under the existing
release gate. On the first authorized natural daily run, verify both protocol rows
exist with server `recorded_at`, report hashes, current cohort counts, and zero
unexpected player identifiers. A failed audit must be visible as a failed workflow
step. No NBA or corrected-CFB edge has been established: the October 3 live scans
were stale, NFL/CFB had zero new quotes, NBA had zero eligible games, and the
private release was blocked by hosted CI and required CodeQL contexts.

Local verification on 2026-10-03: the initial hand-created worker role
lacked the scanner's normal forecast/quote grants, so its failed audit was not
a faithful production-role test. A fresh migrated database followed by normal
`provision_roles` exposed the actual gap: the worker could not read or append
private reports or use their sequence. The provisioning fix passes its restricted
role integration regression and the real `current_multisport_checkpoint --sport
all` entrypoint under that order. The two stored empty-database reports have
64-character digests, `target_verified=false`, and `insufficient_data`. The
full Python suite passes 1,982 tests with 71 skips; the fresh PostgreSQL
migration suite passes 12 and clean-role integration suite 53. These checks
prove the local read/write path, not production history coverage, qualified
picks, or edge. Hosted CI and deployment remain blocked by the account
payment/spending-limit runner state and required CodeQL contexts.
