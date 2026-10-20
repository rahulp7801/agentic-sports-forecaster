# Prepared history display and refresh diagnostics

## Scope

This increment prepares a public descriptive-history renderer and preserves safe
database failure metadata in history refresh snapshots. It does not activate a
private engine, replace the live player-history component or establish new
prospective outcomes.

## Prepared display consumer

`PlayerHistoryDisplay` consumes `linework-forecast-history-display-v1` and checks
an independently supplied expected binding through the existing public decoder.
Revision, forecast/public-record identity, athlete/terms and original source
scope must match before any supplied content appears. A future trusted caller
must resolve that binding separately; copying it from the display is insufficient.

The component renders supplied ten/twenty-record windows, recent and calendar
summaries, roster context, participation labels and card wording. It does not
fetch source logs, choose a model policy, calculate cohorts or recompute supplied
means/rates. It retains missing-stat, tie, incomplete-history, source-correction,
roster and retrieval-limit disclosures. Invalid and unavailable contracts use
generic wording without internal diagnostic reasons or stale summary content.

The public import-closure test includes runtime and type dependencies and rejects
private history producers, immutable resolvers and the existing live component.
Real React server-rendering tests exercise supplied values that deliberately
differ from row recalculation, both initial display windows, independent binding
mismatches, scope labels, unavailable output and disclosures. These tests do not
claim browser interaction or a deployed integration.

Existing live routes, `PlayerHistory`, private producers and engine credentials
are unchanged. This component remains unmounted; the complete public-platform /
private-engine separation still requires reviewed integration and activation.

## Refresh failure diagnostics

The scheduled daily run had reported history `OperationalError` without a
SQLSTATE. `refresh_history` caught the exception before the outer daily stage
could inspect its database cause. The failure snapshot now uses the existing
bounded `error_fields` helper: a sanitized exception class name and, when present,
a five-character SQLSTATE from a bounded cause chain. Exception text, SQL,
parameters, database URLs and credentials are excluded.

Mocked CLI regressions cover connection failure `08006`, cancellation `57014`,
a malformed SQLSTATE containing a private URL, failure exit status and subsequent
successful refresh. Success coverage, status transitions, engine disposal,
source fallbacks, collection behavior and retry policy are unchanged.

The earlier database failure's cause remains unverified. This increment enables
diagnosis on a future ordinary scheduled run; it does not claim recovery, perform
another collection, backfill missing evidence or change settlement admission.
Frozen study implementations, chronology receipts and qualification thresholds
remain unchanged. Raw evidence stays local.
