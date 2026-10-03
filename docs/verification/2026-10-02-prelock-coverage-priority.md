# Pregame quote priority when reserve capacity is scarce

The October 2 read-only scan audit found 57 eligible CFB events, zero attempts, and 57 `pregame_credit_reserve` skips. The rolling 30-day ledger held 441 credits against its unchanged 450-credit cap. At the 21:00 UTC prelock reserve release, only one four-credit event fits while retaining the final four-credit check. Two games begin at 23:00 UTC. Their existing snapshots show zero versus 46 roster-verified forecasts from 12 distinct athletes. Neither has a supported near-pass under the existing threshold, so the previous oldest-attempt tie-break would select the zero-forecast event first. The other opportunity would fall after the one-hour pick lock.

Only inside the existing two-hour-to-one-hour prelock reserve stage, and only after supported near-pass priority ties, the scanner now places a previously evaluated event with more roster-verified athletes first. Alternate lines and markets for one athlete count once. Earlier and already locked windows keep their prior ordering. It uses the already projected bounded snapshot in the same read, requires exact game and sport identity, and refuses a stale, future, malformed, or over-limit snapshot. It does not inspect outcomes, alter model probabilities, lower qualification gates, bypass the staged reserve, raise either credit cap, request additional quotes, or place bets. The existing oldest-attempt rotation still resolves equal coverage. This is a general predeclared allocation rule, not evidence that a previously quoted event will yield a qualified pick or positive return.

Verification uses a scarce-budget integration test with an older empty capture and a later covered capture at the same kickoff: exactly one quote is requested before lock, for the covered game, and the second stays reserved. Other tests preserve supported near-pass priority, 48-hour source freshness, event identity, malformed-snapshot rejection, and existing scan failure handling. After release, inspect the next natural scan at the recorded reserve time, its exact event order and credit ledger, then the immutable forecast and price cohort. Do not trigger a redundant paid scan to validate this change.

## October 3 sample-support refinement

The initial coverage count treated a roster-confirmed athlete with 1-19 prior
games the same as one with the existing 20-game model minimum. At a scarce
prelock credit boundary, a game with many short-history players could therefore
precede one with a player who already has sufficient history for a qualified
forecast. The tie-break now ranks distinct roster-confirmed athletes with
20-40 recorded games first, then all distinct roster-confirmed athletes as a
fallback. A player with alternate lines or markets is counted once in each
applicable tier. This only changes the existing two-hour-to-one-hour prelock
ordering after near-pass priority ties. It does not remove shorter-history
games from the queue or affect the protected final-hour credit, the frozen
model, quote freshness, or qualification minimum.

The integration case retains exactly one four-credit prelock quote and the
remaining reserve when a three-player, 19-game event competes with a
one-player, 20-game event. It chooses the latter. Scanner reliability tests:
30 passed. This is an allocation hypothesis, not evidence of a positive edge;
verify it on the next natural deployed scan and retain the complete event
denominator before comparing any outcomes.
