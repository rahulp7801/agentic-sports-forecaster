# NFL passing and rushing source admission, October 4

The production NFL `pass_yds` and `rush_yds` model used an exclusive game-date
cutoff but did not check when its nflverse weekly rows were observed. A row first
ingested or corrected after selection could therefore contribute to the
recorded probability. The offline current-history replay already applies this
conservative receipt-time restriction, but it cannot reconstruct overwritten
versions of production rows.

The new admission proof adds `BOOL_AND` over the **same selected history rows**
in the original aggregate SQL statement. It checks the nflverse provider,
SHA-256-shaped batch and row commitments, non-null observation time and
`source_observed_at <= history_observed_before`. The same aggregate returns the
selected normalized stat rows; the executor recomputes each stored row digest
and rejects a stale or mismatched commitment. Legacy NFL digests omit only
receptions, which neither core forecast uses. A single statement prevents a
second-read race. The frozen query builder, sample, probability, confidence
interval, model version and threshold remain unchanged. A missing or false
proof leaves the forecast in the research ledger with
`history_source_unavailable`, zero stake and no qualified pick.

From `2026-10-04T19:39:00Z`, new current-version NFL passing/rushing rows must
retain `history_source_admission_policy=nfl-core-history-source-admission-v1`
and `history_source_verified=true` to appear on the pick board or qualify in
the browser. Earlier retained forecasts remain under their original admission
rules. Receiving and CFB keep their already frozen source-as-of paths. The
public explanation describes a missing preforecast history receipt plainly.

Local verification: frozen evaluator digest and affected backend tests **140
passed, 1 optional live-database test skipped**; the earlier full backend run
had 2,152 passes, 72 skips and 12 failures attributable to the then modified
byte-pinned query builder and fixtures. The builder was restored byte-for-byte,
and every failing class was included in the clean focused rerun. Frontend tests
**319 passed**, TypeScript and changed-file ESLint passed. A Webpack production
build is used for this local clone because its shared `node_modules` junction
is outside Turbopack's project root; hosted CI has independent dependencies.

This guard verifies the selected row values against their stored commitments
at selection time. It does not independently authenticate the nflverse provider
or recompute a full-season batch digest from the selected subset.
It does not recover old overwritten stat versions, prove forecast calibration,
establish positive after-price returns, or create a daily pick. Production
deployment remains subject to the existing protected CI/account billing gate.

## Diagnose real source-proof coverage after release

The next fresh NFL scan now records `nfl_core_source_checked` and
`nfl_core_source_verified` for every evaluated passing/rushing **market
selection**, independently of its final qualification reason. An explicit
zero verified count survives when all checked selections fail. The public
slate displays the bounded verified/checked pair for exact matched games and
names `history_source_unavailable` and `source_chronology_unavailable` among
recorded block reasons. This distinguishes a missing source receipt from a
model/price rejection without exposing athlete rows or private source fields.
Counts are selection counts, not independent players, games, wins or an edge.

## Row commitment replay

An integrity follow-up now replays the stored NFL row commitment from the
exact selected rows returned by the same aggregate statement. A changed
passing or rushing value with an unchanged digest fails admission while the
underlying frozen probability still computes. Legacy row commitments are
accepted only in their original format, which includes passing and rushing
values. A disposable local PostgreSQL test executed the real aggregate,
confirmed valid admission, changed a passing value without updating its digest,
and confirmed rejection. The container was removed after the test. The combined
executor, scan, history and frozen checkpoint tests passed **113/113, 3 optional
database tests skipped**. No production coverage or
prospective edge claim follows from this local validation.

A restricted read-only aggregate query against the hosted player-stat table
was attempted on October 4 to measure live source coverage before deployment.
The database host did not resolve from this workstation; no row count was
obtained, no write occurred, and no provider quote was collected. The next
authoritative coverage checkpoint is the first genuinely executing protected
scan after deployment. Focused backend scan tests passed **65/65**; slate
projection tests passed **16/16**, TypeScript, changed-file lint and the local
Webpack production build passed.
