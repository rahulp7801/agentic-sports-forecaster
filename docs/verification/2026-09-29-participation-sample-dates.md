# Dated participation context and nested public projection

## Change

New NFL and NBA descriptive participation summaries retain the oldest and newest game dates separately for recorded participation, recorded zero NBA minutes, and unknown participation. These dates come from the same source-filtered, pre-cutoff, maximum-40-game rows as the existing means and direction hit rates. Empty groups have null date ranges.

The public API validates real calendar dates, group presence, ordering and the exact forecast cutoff. Malformed dated comparisons are omitted while current roster and injury evidence remains intact. Historical comparisons without retained dates disclose unknown recency. The UI shows each group's date range and age before the target game; groups whose newest game is more than 30 days old are explicitly insufficient to establish current form.

The public API also projects nested cohort objects to the three documented statistics rather than passing through unexpected fields. This closes an accidental data-disclosure boundary; no actual credential disclosure is established by this code finding.

## Invariants

No probability adjustment, model/evaluation change, qualification relaxation, provider request, paid-credit use or historical forecast rewrite. Unknown participation remains separate from verified zero NBA minutes. NFL missing and zero snap counts do not prove absence. Dates are not retrospectively fabricated for older forecasts. The staged reserve and 20/450 caps remain unchanged; PR #194 remains excluded.

## Verification

Unit and public-boundary tests cover invalid and missing dates, source cutoffs, separate cohorts, empty groups, legacy evidence, private nested-field removal, round-trip projection and unchanged current availability. PostgreSQL tests execute the actual NFL and NBA queries with late observations and explicit zero NBA minutes. Read-only hosted probes verify real date aggregation; all live research artifacts stay local.

At the next natural scan, inspect a new dated comparison and its public projection. Existing recorded forecasts continue to display the explicit legacy limitation.
