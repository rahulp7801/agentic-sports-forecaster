# Forward NFL stat-only receiving paper candidate

Version: nfl-stat-only-shadow-v1. Policy: complete-receiving-stat-only-transfer-v1.
Freeze: 2026-10-04 00:00 UTC. Artifact SHA-256:
cfcf0c9e57d3027fcc21e9a105bab03752f80c1a0b4684efa2ab7c09bbdfe35f.

The frozen parameters are the broad, 2024-fitted corrections selected on
September-October 2025 in the [stat-only research replay](2026-10-03-nfl-stat-only-exploratory.md).
The later corrected-history transfer was a sensitivity check, with no refit.
This version is untraded research. It is not a dashboard probability, suggested
pick, stake, win-rate claim, or proven market edge.

The candidate reads only an existing, server-recorded recent-role receipt from
a saved NFL forecast. That receipt must replay the corrected 20-40 played-game
history, source commitments, roster identity, pregame observation cutoff,
exact offer, and production baseline. The new correction uses receiving yards
or receptions, recent hits, recent mean, team history, and days since the last
game; it uses no target-count feature. It requires an offered half-point line
of at least 19.5 receiving yards or 2.5 receptions and checks that its
probability curve is nonincreasing over prior stat thresholds. Unsupported
or noncausal inputs produce a bounded unavailable reason.

After each NFL event is saved, a separate paper stage chooses the earliest saved
attempt per player, game, and prop before examining model status or outcomes.
It makes no sportsbook or odds API request. It appends a receipt under one
protocol per prop in the existing private analytics.paper_selections table.
The database stamps recording time and enforces the quote expiry and
append-only key. Capturing after each event keeps early quotes from expiring
during a long all-sport scan. The scan bounds each research capture to six
seconds and isolates its failure from the production scan result. The daily
runner reuses the event capture status instead of repeating a late scan-wide
read; existing workload research remains separate. No provider request is added.
The worker Docker allowlist includes only the pinned parameter JSON.

Read-only audit joins each receipt to its original saved forecast and
authenticated settlement. It checks receipt hash, protocol, exact offer,
original forecast hash, decision and expiry, role proof, candidate replay,
server recording time, and same-book recorded market midpoint. It chooses
attempts before status or outcome filtering. The report counts unavailable,
unpaired and unsettled attempts separately. At least 50 paired settled games
per prop are needed before a descriptive status can indicate candidate
probability support; both Brier and log-loss game and player intervals must
favor the candidate against production and market. A corrupt paper receipt
blocks any favorable status. Promotion and edge_established remain false.

Next evidence checkpoint: a genuinely deployed scan after the freeze must
show nonzero research:stat-only-capture:nfl attempts and server-recorded
receipts. After games finish, stat-only-shadow-validation:nfl must show
authenticated paired outcomes. No retrospective 2025 result can substitute
for those prospective outcomes or for a price-based return and CLV review.

Local verification: 1972 passed, 71 skipped in the final local full suite.
Hosted CI and production remain blocked by the GitHub account payment or
spending-limit state. The user requires zero spend, so the $0 budget stays.


## October 3 evaluator integrity check

The read-only paper audit now replays **every selected** stat-only receipt, including
legitimate unavailable results, against the original saved forecast and checks
that the database recording time was within the same pregame quote window.
The paper loader also rejects a malformed non-object shadow instead of
letting it disappear from the evaluated cohort. A wrong version, changed
probability, extra field, or late receipt increments
`invalid_shadow_receipts` and sets every market and the overall report to
`invalid_shadow_receipts`. It cannot be silently dropped while the remaining
rows produce a favorable probability-support status. A replayable abstention
remains an unavailable attempt in the fixed denominator. The frozen model,
parameter artifact, implementation hash, selection timing, qualification
thresholds, and consumer predictions did not change. Local verification:
15 focused paper tests, 1,991 backend tests passed (71 skipped), and Bandit
passed. No post-freeze production receipt has been collected because hosted
Actions has not started the scheduled scanner.

## October 3 capture timing fix

The forward paper decision is now recorded immediately after each NFL event's
saved forecast is published, before the scanner quotes another event. A bounded
event query selects only that scan and game. Research capture failures are
reported as degraded research coverage and do not turn a completed consumer
event into a failed one. The existing database clock still rejects late writes.
This changes collection timing only; it does not change the frozen candidate,
cohort definition, quote validity, or dashboard picks. Production evidence is
still pending a hosted scan after the freeze. The scanner failure and timing
regressions passed, and the complete local backend suite passed 1,995 tests
with 71 skipped. Hosted PostgreSQL and deployment checks could not run while
GitHub Actions was blocked before job steps.

The cached local PostgreSQL 16 image allowed a disposable, loopback-only
verification while hosted runners were unavailable: all 12 migration tests
and 54 CI PostgreSQL integration tests passed. The new integration regression
uses the actual append-only table and server clock to verify one-event
selection, an idempotent retry, an expired quote, a future decision, and the
receipt hash. It stubs the model solely to isolate database timing; the frozen
candidate replay remains covered by separate tests. The full backend suite
without a database passed 1,995 tests with 72 skipped, including this
database-only regression. No production database or provider was contacted.
