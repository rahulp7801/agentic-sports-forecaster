# NFL receiving history archive

## Scope

Stage verified missing NFL receiving history in two restricted append-only tables. This release adds no model, dashboard-history, qualification, settlement, or quote-collection reader. Activation requires a separate versioned input policy and prospective evaluator; existing frozen role and workload experiments remain unchanged.

## Evidence and review

The offline importer uses the existing explicit-final ESPN verifier: exact player crosswalk, completed regular-season game, event roster, gamesPlayed, explicit receiving values and independent nflverse offensive participation. Missing passing/rushing values remain NULL. Every event must match the stored schedule. Existing primary receiving values must agree and have valid row provenance; conflicting evidence fails the whole plan.

Preview is read-only. Apply requires an exact positive count and deterministic plan SHA. It briefly holds SHARE locks on primary NFL history and games (5-second lock timeout), replans inside the transaction, and writes only the source archive and supplements. Exact UTF-8 bundle text is retained with a database-verified SHA. A second application requires a new preview and cannot overwrite retained evidence. Primary ingestion that later supplies a matching record is recognized as complete.

## Access and chronology

Worker grants are SELECT and INSERT only. PUBLIC, browser roles and dashboard role have no access. No raw source material is added to public snapshots. Both source observation and database insertion timestamps are retained; identity receipt timing participates in availability. Future activation must gate on both timestamps and current game identity, prefer matching primary data, and reject conflicts.

## Verification

Unit cases cover explicit zeroes, unknown other categories, primary arrival, source conflicts, invalid provenance, DNP, schedule mismatch, duplicate identities and replay. PostgreSQL CI exercises migrations, browser and worker privileges, exact-count application, raw-row preservation, check constraints and atomic replay. No paid requests are part of this workflow.
