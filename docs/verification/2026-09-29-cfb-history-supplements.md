# Archived CFB receiving supplements

## Storage and evidence

Migration 0031 adds an immutable source-bundle archive and append-only receiving supplements. Each supplement binds a primary athlete/event/revision, the original normalized row, source asset commitments, explicit final receipts, the exact fields supplied, and the effective full-row hash. Existing passing/rushing statistics and non-null receiving statistics are preserved.

The restricted effective-history view uses a supplement only while both the primary record hash and every original core field still match. A refreshed release with identical normalized statistics retains the supplement; changed statistics or identity invalidate it. Original rows and prior supplements remain available for inspection. A changed primary revision can receive a separately reviewed supplement.

Browser roles and the dashboard role have no access to the archives or effective view. The worker receives SELECT and INSERT on supplement tables and SELECT on the view, with RLS on underlying tables and a security barrier on the view. UPDATE, DELETE and TRUNCATE are not granted. Archived text is checked against its SHA-256 by PostgreSQL.

## Review and application

```text
python -m sportsbet.quant.cfb_history_supplements --bundle PATH
python -m sportsbet.quant.cfb_history_supplements --bundle PATH --apply --expected-count N --expected-plan-sha256 DIGEST
```

Preview uses a read-only hosted snapshot. Application locks scoped primary history, repeats source and conflict validation, and requires the exact reviewed plan digest and count. It inserts the bundle and supplements atomically without modifying primary history or forecasts. Replaying an applied plan fails the reviewed-count check. Conflicting retained evidence is never overwritten. Receipts are loaded from the supplied archive; this command performs no collection.

## Activation boundary

This release provides restricted storage and a verified effective view. The production model, public history view and frozen evaluation continue using the primary history until a subsequent coordinated reader change introduces an explicit prospective input-policy version. Staging supplements does not itself repair consumer predictions. The next release must integrate model/history/settlement readers consistently, validate retained settlement proofs, and keep existing frozen cohorts separate. No edge is inferred from corrected historical averages.

## Tests

Unit tests cover preserved primary rows, complete effective record commitments, partial missing fields, conflicting source identity/statistics, retained-evidence conflicts and replay planning. Disposable PostgreSQL tests cover atomic application, stale-plan rejection, exact effective values, raw-row preservation, stable refreshes and changed-source invalidation. Migration tests exercise browser denial, worker append-only privileges, security-barrier/RLS settings and downgrade/upgrade behavior.
