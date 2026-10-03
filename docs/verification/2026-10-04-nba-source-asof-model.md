# NBA scan source-time cutoff, separate model cohort

The scheduled scan already saved `selection_time` in GraphState as
`observed_before`. The NBA quant agent omitted it from `PropParams`, so the
game-log query could include a row first ingested or corrected after the
forecast. `NBAQueryBuilder` already has a parameterized
`source_observed_at <= $N` clause and applies it before the most-recent-N
selection; the agent now passes the recorded timestamp into that clause.
Because the database's older NBA provenance constraint is `NOT VALID`, the
new source-time path also requires an `nba` or `espn` provider and both
64-character lowercase hexadecimal batch and record hashes before selecting
recent games. Older rows with only a timestamp remain unavailable rather
than becoming an unproved preforecast sample. These hashes are stored ingest
commitments; the query does not replay the raw provider response on every
request.
The existing date cutoff still excludes the target and later games. The
fallback query also retains both cutoffs while dropping only the unsupported
matchup filters. No injury status or teammate effect is inferred from a
game-log row.

This changes the population and sometimes the probability, so scans at or
after **2026-10-04 03:00 UTC** use
`empirical-jeffreys-v4-nba-source-asof-v1` with policy
`nba-source-asof-v1`. Earlier v4 NBA forecasts retain their original version,
policy absence, and metric cohort. New records must carry the source cutoff
between the freeze and model capture; the existing immutable quote commitment,
pregame check, confidence gate, and availability gate remain required. The
consumer signal projection retains the exact new policy, recognizes the new
version for current suggestions, and treats old v4 as historical. The live
signal also carries its recorded source cutoff; the browser gates a new NBA
suggestion unless that time is after the quote and freeze and no later than
the forecast capture, which must precede game start. A missing or changed
cutoff becomes `source_chronology_unavailable`, never a current suggestion.
Neither a
backfilled row nor a later correction can be silently counted as known at an
earlier forecast time; an unavailable source leaves an estimate unavailable.

The new version contract and `ReleaseLedger` live in a separate module.
They reuse the unchanged v4 exact-quote parser only after validating the new
NBA version, source time, policy, and pregame chronology. The scan and daily
consumer paths use that derived ledger on both admission and read; invalid
new-version rows are excluded from public predictions and counted in the
base report's excluded metadata. The byte-pinned `model_contract.py` and
`ledger.py` remain unchanged so the old prospective evaluators continue to
verify their original source commitments.

This repair makes the source chronology of **future** NBA predictions more
defensible. It does not demonstrate a betting edge, change frozen NFL/CFB
evaluation cohorts, promote a research pick, request odds, or spend credits.
The protected private release still needs runnable CI, merge, deploy and live
as-of API checks before the consumer site can use it. Post-deploy verification
must inspect a new NBA scan receipt with the new version and cutoff and
authenticate its later results against the matching recorded prices.

Local verification before the cohort freeze: **2,028 backend tests passed**, 72
were skipped (including tests requiring a disposable PostgreSQL service);
**294 frontend tests passed**, TypeScript and targeted ESLint passed, and the
production Next.js build succeeded. Focused tests cover a source row arriving
after the forecast, an unhashed older row, agent cutoff forwarding, a forged
cutoff rejected on both write and read, retention of the old v4 metrics,
exact new policy on the
consumer pick board, and old NFL/CFB frozen evaluator commitments.

## Pregame team/rest context uses the same source cutoff

The pre-release NBA source-asof scan passed `observed_before` to the probability
query, but its preceding context producer chose the player's latest team and
rest days from a separate game-log query that only checked the game date. A
late backfill or correction could therefore decide home/away and opponent
filters for a model estimate even when the probability history excluded that
row. Future source-asof v1 context selection now also requires the recorded
source cutoff, an allowed NBA/ESPN provider, and both valid source hashes.
No eligible pregame row yields no inferred team/rest context. The original
pre-freeze v4 context query is retained for historical replay. The source-asof
v1 release remains in the unmerged private PR; the deployed NBA board has
no v1 predictions. The frozen NFL/CFB and Kalshi paper populations are
unchanged. Focused NBA context/as-of/query tests pass 31/31; full backend
passes 2,108 with 72 skips and seven existing warnings. No provider call,
credit, bet or order was made by this repair.

The scanner's player-name-to-ID lookup was a second pre-model chronology gap:
it searched all NBA game-log rows, including later backfills, before assigning
the model cutoff. The source-asof v1 path now fixes one cutoff before that lookup
and applies the same provider, two-hash and availability predicates. It groups
the name/ID alternatives before filtering, so the cutoff applies to both.
The identical cutoff flows into the NBA context and probability history. NFL,
CFB and original NBA v4 retain their prior lookup and selection-time behavior.
Three-sport scan plus NBA context/as-of tests pass 52/52. This is a pre-release
source-identity repair, not a new observed pick or performance result.
