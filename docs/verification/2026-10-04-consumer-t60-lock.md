# Consumer T-60 qualification boundary

The immutable pick board selects only recommendations captured by one hour
before kickoff. The public forecast view previously checked fresh price,
availability, and whether the game had started, but it could still present an
earlier accepted snapshot as a **live suggested pick** during the locked hour.
A stale CDN response could also cross the board lock.

The public signal boundary now marks unretained forecasts `game_locked` at
`game_start_time - 60 minutes`, sets their displayed stake to zero, and keeps
the original probability and source evidence as a research record. The
qualified endpoint's shortlist becomes empty at that exact boundary. Its
live CDN deadline includes the same lock so a response containing a suggested
pick expires before it. The empty-board research watchlist stops offering
repricing leads at the lock. The evidence panel labels the expired decision.
Previously locked and historical board records still replay at their original
capture time and retain their original recorded state.

Worker admission and the ledger's second reservation check now use that same
T-60 constant. A context query or database wait crossing the lock records
`game_locked` with no new research exposure. This prevents future accepted
records from entering recommendation metrics when the board could never have
published them. Existing historical receipts and their evaluations are not
rewritten; they still require explicit cohort inspection.

The upcoming-games slate also closes its pick status at exactly T-60, while
keeping captured model/acceptance counts clearly labeled as past scan context.
It hides quote and reserve windows at or after the lock and reports a live
game only after a fresh post-kickoff schedule observation. Its CDN lifetime
expires before both the lock and kickoff, so a cached prelock status cannot
cross either transition. These changes affect presentation and caching only;
the scheduled collector still follows its original cadence.

This enforces the existing board policy without changing the model,
probability, original worker receipt, market quote schedule, monetary API
limits, qualification probability threshold, or frozen evaluation cohorts.
It does not create a pick or establish a market edge. The exact-boundary
regressions and full frontend suite pass **313/313**; focused backend
scan/reservation/board tests pass **100/100**, and the full backend suite passes
**2,079/2,079** with 72 optional database tests skipped. Changed-file ESLint,
TypeScript, and the production Next.js build pass. Production verification
requires a protected merge and deployed live or synthetic accepted snapshot;
hosted CI currently fails before any job step under the account spending gate.
