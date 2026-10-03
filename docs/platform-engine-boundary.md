# Public platform read boundary

The public platform can display reviewed engine output without containing the
forecast, context reconstruction, ranking or qualification implementations.
`frontend/lib/ownerEngineRead.ts` supplies the server integration;
`frontend/lib/engineTransport.ts` supplies bounded HTTP transport. Neither
module imports those private implementations.

This adapter is prepared for integration. Existing live routes have not been
switched to it, no engine origin or credential has been provisioned, and the
current frontend is not yet a clean public export.

## Public historical walkthrough

The landing walkthrough now selects fixed records from
`frontend/data/week-one-demo-display.json`. Its probabilities, final stats,
source commitments and descriptive history summaries are retained display
outputs. `weekOneDemo.ts` grades the three recorded over forecasts and selects
their summaries; it performs no model inference and imports no full history
input or qualification implementation. A source-closure test permits only the
reviewed component, stylesheet, selector and display fixture.

The walkthrough preserves correct and missed examples. It identifies the
September 18 retrieval after the target games, the actual prior-history date
range, and the absence of current-form or pregame recommendation evidence.
Public navigation leads to the waitlist; the owner-only game-log API is not
linked from the demo. Full historical inputs and retrospective research exports
remain outside this reviewed display closure. Preparing these sources does not
publish a repository, establish an edge, or complete the live engine split.

## Forecast display authority

The existing private `forecastPage.ts` producer now adds a `display` receipt to
its unchanged server-selected signal rows. `forecastDisplayProducer.ts` retains
private grouping and lifetime calculation; `forecastDisplayAuthority.ts` contains
only public metadata types, bounded projection and conservative clock handling.
The protocol is `linework-forecast-display-v1`.

The receipt names the evaluated time, revision, requested view, completeness,
invalid-row count, original row order, primary/alternative relationships and
explicit state. Qualified rows have an `actionable_until`; watchlist rows have
no action deadline and remain descriptive until their producer-issued lock;
library rows are research with no current-action lifetime. Original source-age
gates allow equality, so the producer uses the first excluded integer
millisecond; game lock equality remains excluded. An elapsed primary withholds
its alternatives without promoting another record or changing surviving ranks.

The metadata reader requires separate page/request bindings for revision, view,
completeness and invalid-row count, and matches each ordered signal ID, explicit
boolean gate and reason. It copies only approved metadata fields. It does not
validate or return full signal metrics, source evidence or retained board records.
Before replacing client qualification, a complete public signal projector must
bind those records to this receipt and the authenticated resource envelope.
Recorded, locked and final board records require their own contract.

Current browser qualification and ranking have not been replaced by this
receipt. Those existing checks remain while the full producer/consumer
integration is prepared. Archive page accounting now includes display metadata,
multibyte signal content, game rows and reserved outer-envelope bytes before
advancing the cursor. Oversized responses fail closed.

The results component's complete source closure, including type imports, is
separate from private board/qualification code. Labels and board output types
live in public display modules; simple display math and calendar classification
are extracted without changing their implementations. Remaining private client
dependencies must still be removed before the clean public export.

## Request contract

An API handler supplies its resource and a domain-specific public projection:

```ts
import {ownerEngineRead} from '@/lib/ownerEngineRead';

// projectDisplay validates the display contract and copies only approved fields.
// It must not return the input object unchanged or calculate qualification.
return ownerEngineRead(request, 'signals', projectDisplay);
```

The wrapper is marked `server-only`. It uses the existing owner-session guard
before reading configuration or contacting an engine. The engine destination
and read credential are server variables, `PRIVATE_ENGINE_ORIGIN` and
`PRIVATE_ENGINE_READ_TOKEN`; they must never use a `NEXT_PUBLIC_` name or be
passed to a Client Component.

The destination is one configured HTTPS origin with no user information, path,
query, fragment or custom port. The caller cannot choose an upstream URL.
Registered resources are benchmarks, gamelogs, games, kalshi-research, markets,
metrics, picks, polymarket, prop-screens, scans, signals and slate. Each resource
must match the incoming `/api/<resource>` path. Existing request admission
rejects unsupported, duplicated or unbounded query parameters and foreign
browser requests. Only reads are supported; no collection, order, bet or
administrative endpoint is exposed.

The adapter sends one `GET /v1/display/<resource>` request. It forwards only the
admitted query, an Accept header and the service bearer credential. Visitor
cookies, authorization headers and diagnostic headers are not forwarded.
Redirects are refused, credentials are omitted and shared caching is disabled.
There is no retry or local inference fallback.

## Response contract

The engine sends exactly these six envelope fields:

```json
{
  "protocol": "linework-display-v1",
  "resource": "signals",
  "generated_at": "2026-10-13T15:00:00Z",
  "expires_at": "2026-10-13T15:01:00Z",
  "revision": "<64 lowercase hexadecimal characters>",
  "data": "<resource-specific display object>"
}
```

The example is a schema illustration, not a live forecast or evidence receipt.
The engine chooses display expiry using its unchanged qualification and
chronology rules. Public code checks expiry and may withhold expired output;
it cannot extend expiry, reconstruct an approval, change a probability or
promote a previously blocked record. Revision identifies the retained output
version, not a statement of predictive performance.

The adapter accepts only a direct HTTP 200 JSON response, with a maximum body of
one MiB. An eight-second deadline covers fetch and streamed body reads; caller
cancellation also stops reads. Protocol, resource, revision, timestamp shape,
future clock bound and unexpired display lifetime are checked before projection.
Expiry is checked again before replying. The required projection validates the
resource schema and returns an explicit allowlisted plain JSON object or array;
`null`, missing data, asynchronous results, getters, nonfinite numbers, exotic
objects, excessive nesting, exceptions, serialization errors and oversized results fail
closed. The configured service credential is also barred from the serialized
reply.

Projections must preserve original source timestamps, capture dates, model
versions, uncertainty and evidence status. They must exclude raw evidence,
private configuration, model parameters, credentials and implementation code.
A valid transport envelope alone does not certify those domain facts.

### Forecast record projection and integrity binding

The current private signals producer issues a `linework-forecast-record-binding-v1`
binding with resource `signals`, the exact sport/view/offset/limit/revision/player
request and a SHA-256 commitment. The commitment covers that context and the
entire serialized page, including records, games, source/context fields, display
authority, coverage and pagination. Canonical JSON sorts object keys and retains
array order. The existing one-MiB, 50,000-node and depth bounds are retained.
Library rows are accounted for before consumption against both byte and node
budgets, preserving a continuation cursor when dense context fills either budget.

The public decoder verifies the commitment and request, then explicitly copies
approved signal/game/evidence fields. Probabilities, uncertainty, model versions,
timestamps and gate flags are supplied outputs. It does not dispatch on model
versions, reconstruct source admission, calculate qualification or rank records.
Unknown raw fields are excluded from its returned object. A matching ID cannot
attach a receipt to changed odds, lines, metrics, context or game time.

`fetchForecasts` now consumes this contract and supplied primary/alternative
order. It can withhold elapsed approvals, including every alternative of an
expired primary, but cannot promote an alternative. Watchlists remain gated and
descriptive until the issued board lock; research archives remain descriptive.
Incomplete or invalid qualified coverage has no live output. Unsigned legacy
responses are rejected rather than importing a private browser fallback.
Stable research revision/search/cursor identity and verified partial-page
recovery are retained.

This hash is integrity metadata from the authenticated owner API, not an
independent authenticity signature. The existing API currently produces the
packet; it has not been switched to a configured private engine. Integration
must also bind the domain revision to the outer engine envelope and verify the
real service. Recorded, locked and final board records require a distinct
contract and must never use current-live expiry to revive historical approval.

The strict fetch/decoder/Arbitrage source closure has six runtime sources and
seven including declaration-only types, with no private implementation. Other
clients still reach private code. In particular, model-specific history cutoffs
and reconstructed descriptive cohorts in `forecastHistory`, plus mixed
admission/presentation modules for participation context, remain outside the
public allowlist. A private history producer must resolve a stored forecast by
ID, preserve its original selected-source and capture cutoffs, and emit bound
summaries before those imports can be removed. Browser-supplied later cutoffs
cannot become source authority.

### Prepared descriptive-history output

`forecastHistoryDisplayProducer` wraps the unchanged private history/form/card
helpers. It emits ten/twenty-record windows, disjoint latest/previous five-game
summaries, calendar/current-roster-team summaries, card wording and participation
date labels. Missing stats, ties, old teams and retrieval limits remain explicit.
The public `linework-forecast-history-display-v1` decoder copies those supplied
outputs and validates their structural coherence; it does not choose history
rows, dispatch on model versions or recalculate means, direction rates or a
forecast probability. Participation formatters now live in a public module,
separate from the unchanged private cohort validators.

The mandatory binding contains revision, forecast ID, the complete normalized
public-record commitment, athlete/terms, original capture, exclusive game-date
cutoff, selected source-time cutoff and its producer-issued kind. Unavailable
history contains no summary/card data. A mismatched source-read cutoff remains
unavailable. This preparation has no live-approval or settlement state and does
not switch history routes or browser components to a new service.

`forecast_record_sha256` hashes canonical projected public fields; it is **not**
the immutable ledger's `payload_sha256`, which hashes original stored TEXT bytes.
An actual private resolver must verify the retained database receipt, preserve
timestamp precision and separately map that raw commitment to the approved
public record. Current snapshot-window revisions are mutable output revisions,
not pregame receipt proof. Never query a raw ledger commitment using the public
display digest or upgrade an old export without receipt columns into such proof.

The dashboard role has no access to `analytics.predictions`. Immutable forecast
resolution must stay in the private engine; replacing public reader credentials
with worker/owner credentials is outside this boundary. History reads must then
derive exact athlete/stat and both cutoffs from the resolved record. The current
history views retain selected forward corrections rather than every original
model input. A matching trusted read descriptor does not independently prove
per-row source availability or a complete model sample; retain the existing
source SQL/commitment checks and expose earlier-version gaps as unavailable.

### Prepared immutable history resolver

The private `immutableForecastReceipt` reader verifies the original UTF-8 ledger
TEXT before JSON parsing. It requires an exact five-field database row, matching
opaque forecast ID and raw payload SHA-256, non-null receipt fields and the UTC
database timestamp with all six fractional digits. JSON and TEXT retain bounded
size, nesting and node counts. Legacy exports, parsed/reformatted payloads,
millisecond `Date` receipts and malformed rows cannot substitute for that receipt.

`resolveImmutableForecast` accepts only ID and raw payload commitment, then
prepares a parameterized lookup against `analytics.predictions`. A private reader
callback is required; this helper opens no connection or route. It projects the
original athlete/stat, terms, quote/capture/start timestamps, model/source policy,
game-date cutoff and captured roster context. It returns separate receipt
metadata and a derived as-of query, excluding the raw payload and model metrics.
It does not fabricate the full public EVSignal fields absent from the ledger.

Quote, model generation, source selection, capture, database receipt and start
are compared at microsecond precision. The original known model-version policy
mapping selects its retained source timestamp; legacy versions use original
capture. Strings and timezone offsets are retained in the query. The receipt must
precede start and cannot widen either history cutoff. Exact stable IDs select
history; NFL passing/rushing uses the existing primary-source version view.
Browser-supplied scope, athlete, terms and later cutoff overrides are rejected.

Synthetic review reproduced an invalid rejection when valid capture, receipt and
start all fell within one millisecond. The new resolver compares their retained
microseconds directly. Existing history helpers remain unchanged and their
millisecond chronology still requires a precise private adapter before this
resolver can feed the prepared history-output producer. Array-valued enums cannot
coerce into a sport, stat or observed roster status and bypass source routing.

This resolver is preparation, not a verified database/service integration. Its
raw ledger commitment still needs an independently resolved approved public
record mapping, a trusted scoped history reader and the existing per-row source
commitment checks. No dashboard credential or role grant is widened. The current
views' earlier-version gaps remain unavailable; these queries do not reconstruct
every historical model input or establish pregame performance evidence.

### Prepared immutable history output bridge

`buildImmutableHistoryDisplay` now connects the prepared receipt resolver to an
independently read, revision-bound approved public record and a trusted history
reader callback. It requires both distinct commitments. The approved record is
projected and hashed canonically, then matched to original history identity,
terms, timestamps, model/source policy and retained roster state. Numeric
forecast outputs remain independently supplied; this descriptive bridge does
not certify raw-to-public model-metric parity or create a new probability.

The history callback receives only the resolver's fixed SQL and derived
parameters. At most twenty dense row wrappers are accepted. Wrong or missing
athlete IDs, dates at/after the retained exclusive cutoff, duplicate games and
malformed records fail admission instead of silently becoming empty history.
NFL passing/rushing source rows pass the unchanged ingestion-commitment verifier
before public log projection. Empty successful reads retain empty descriptive
windows and null rates; unavailable readers contain no calculated/card data.

Callback data is copied through own data descriptors with incremental one-MiB
UTF-8 JSON, depth and node bounds. Request values and reader functions are
snapshotted before awaits. Private receipt data, raw payloads, queries, source
rows and upstream errors cannot enter the returned display DTO.

The separate private calculation path copies original statistical calculations,
team aliases and card wording after precise receipt admission. It consumes the
resolved subset directly and never fabricates full EVSignal metrics or adjusts
timestamps to pass old guards. The original history/card helpers remain
unchanged. The immutable bridge omits participation labels until their complete
retained split provenance is resolved; later presentation enrichment cannot
become original context proof.

No real readers, database access, route switch or private engine service are
activated here. As-of availability still relies on the unchanged SQL predicate
and trusted reader: returned history rows omit availability timestamps. NFL core
commitments cover their retained athlete/team/stat fields rather than complete
schedule history or model inputs. Earlier source-version gaps remain missing.

The public response retains the envelope with projected data and three no-store
cache headers. Upstream error text, headers and cookies are never reflected.
Failures return a generic 503; denied owner sessions retain the existing 401.
HEAD performs the same validation and returns no success body.

## Release requirements

Before switching a live route or publishing a clean platform export:

1. Implement and verify the private producer and each public display projection.
2. Move qualification, ranking and model reconstruction out of client imports
   and the public source allowlist. Keep frozen studies and rules unchanged.
3. Verify complete import closure and inspect actual browser/server bundles and
   CI artifacts for private code, research records and model artifacts.
4. Verify real owner OAuth, durable waitlist behavior, API containment and
   display expiry against the configured engine.
5. Pass the existing CI, schema and deployment gates. Follow the reviewed
   repository identity handoff before publishing at the original URL.

The adapter tests use synthetic upstream responses and real encrypted local
owner-session fixtures. They perform no live quote reads, collection, purchases
or transactions. They do not establish an edge or production deployment.
