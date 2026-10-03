# NFL forecast-time form after a later matching primary row

The restricted NFL game-log projection used the current effective row. When a
verified receiving supplement was available first and a matching primary stat
row arrived later, the effective view switched to the primary. A request
bounded by the earlier forecast capture then filtered out that later primary
and lost a game that had been source-available at the time.

Migration 0043 retains the earlier supplement in the restricted
`dashboard_gamelog_versions` view only when the primary has the same team,
receiving yards, and receptions, the archived game and source manifest match,
and the primary observation time is later than both the supplement observation
and insertion times. The NFL game-log API selects the latest row available at
the requested cutoff, as it already does for CFB. Conflicting sources stay
excluded. The supplement has unknown passing and rushing fields; it does not
borrow later primary values. No model reader, stored probability, frozen
evaluation, qualification rule, or paid collection path changes.

A disposable PostgreSQL fixture proves the row is absent before supplement
availability, present with unknown rushing at the earlier capture, and
replaced by the richer primary only after its observation. It also checks
conflict exclusion and restricted role access. Focused NFL/CFB/as-of tests:
3 passed. Fresh-database migration and downgrade suite: 12 passed.
Frontend suite: 309 passed. This corrects a narrow consumer context gap;
it does not establish a win rate or market edge. Production behavior requires
the protected release to pass CI, deploy, and pass the existing three-league
as-of API readiness probes.
