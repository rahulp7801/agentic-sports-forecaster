# Read only the capture value when verifying publication

## Observed failure

Natural monitor `39273528562` on `dd0a766ec01ca7919a52aa000185d18638e31c9d` recorded an NFL publication `OperationalError` with SQLSTATE `57014`. Its report contained no completed NFL market capture clock. NBA remained observed, with an original capture clock in the report. The report validator accepted three receipt entries; that count does not mean three database reads succeeded.

The separate CFB receipt read failed with `ConnectionFailure` / `08006`, and the main receipt read failed with `QueryCanceled` / `57014`. Neither verifier logged a completed verified count, failing key or number of earlier successful reads. The private/landing HTTP verifier was not reached. The public preview's earlier successful contained release remains separate evidence.

PostgreSQL documents `57014` as [`query_canceled`](https://www.postgresql.org/docs/current/errcodes-appendix.html). The code alone does not establish its trigger, actual hosted role settings, a payload-size cause or a connection infrastructure cause.

## Concrete inefficiency and change

The receipt verifier fetched the complete JSONB snapshot, although its acceptance check uses only `captured_at`. Market payloads include unrelated quotes and source metadata. Return only `payload -> 'captured_at'` through the same parameterized primary-key lookup, then provide that value to the existing exact comparison.

The JSONB [`->` operator](https://www.postgresql.org/docs/current/functions-json.html) retains the field's JSON type. Do not convert it to a PostgreSQL timestamp, use `updated_at`, normalize equivalent timestamp strings or replace missing source clocks. JSON null, missing fields, non-object payloads and non-string capture values still cannot satisfy a valid report receipt. A missing row still fails.

Connection options, the five-second statement timeout, read-only mode, query count, failure stages, SQLSTATE reporting and no-retry behavior remain unchanged. Publication batching, frozen source/model/evaluation files, qualification rules and collection budgets are unchanged. This reduces returned data and client decoding work; it does not establish that the observed publication cancellation or connection failures have recovered.

## Verification and next checkpoint

Mocked tests retain the exact parameterized lookup, connection options and failure propagation, including the observed `57014` read cancellation. They reject equivalent-but-different timestamp strings and wrong JSON types. A real disposable PostgreSQL test covers valid, missing, null, scalar and malformed capture values, an irrelevant large payload, and exact clock retention using the actual driver.

The focused local run passed 80 tests. Five database cases skipped because no disposable PostgreSQL URL was configured locally; the new projection regression is among those cases and must pass in real CI. One unrelated CFB CLI integration test was deselected locally; it remains in the required full backend suite. Local test URLs point only at loopback, and no production database or provider is accessed.

Required CI, the real PostgreSQL job and final CodeQL must pass before merge. Inspect the next natural scan on the merged revision for actual publication status and independent receipt verification. Do not recollect quotes or retry uncertain writes to manufacture a successful result. The generic owner-auth readiness gate can remain held by the intentionally retained perimeter restriction until owner OAuth setup and its separate protected release are complete.
