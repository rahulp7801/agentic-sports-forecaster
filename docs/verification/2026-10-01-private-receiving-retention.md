# Private prospective NFL receiving audit retention

The frozen nfl-receiving-individual-pick-audit-v1 protocol begins at
2026-10-01 13:00 UTC. The daily NFL-capable data workflow now runs its
unchanged evaluator after the existing collection step. It reads original
raw-model paper receipts, forecast evidence and authenticated settlements
inside one repeatable-read, read-only snapshot. It then appends the full report
to analytics.prospective_audit_reports through the restricted sportsbet_worker
role. The table has database-owned recording time, a SHA-256 payload check,
row-level security and no worker update/delete privilege. Browser roles have
no table or sequence access.

The public GitHub job prints only whether private retention succeeded. The
report, selection IDs, source receipts, results and individual picks are not
uploaded as artifacts or written to public logs. A failed research step is
visible in Actions but cannot erase public forecasts or cause a paid retry.
The worker may read the latest private report through its protected database
connection; keep any exported copy outside the public repository.

This adds no provider request. It does not alter model probabilities, frozen
evaluation rules, public qualification, quote cadence, the 20-credit daily or
450-credit rolling limits, or the staged pregame reserve. Reports always retain
the frozen evaluator's promote=false and target_verified=false fields. Review
still requires the closed first-50 cohort, at least 25 games, authenticated
settlements, game-cluster intervals, matching-price returns and independent
judgment about multiple tested strategies. A stored report alone is not an
edge or 75% accuracy claim.

The protected master CI migration gate must reach revision
0038_private_prospective_reports before the next daily data workflow runs.
Disposable PostgreSQL tests create the restricted worker role before upgrading,
verify browser denial and worker insert/select, reject worker mutation, and
check the database timestamp trigger. Local unit tests cover payload binding,
nonpromotion, hashing and damaged receipt references.

A separate, manually dispatched private-receiving-audit.yml workflow can append
the same frozen report after 13:00 UTC if the scheduled daily collection is
dropped. It uses only the restricted database secret, requires master and the
production environment, checks the hosted schema, and has no provider key or
public artifact. This recovers evaluation visibility only; it does not collect
new quotes, create picks, or fix the underlying scheduler gap in issue #297.
