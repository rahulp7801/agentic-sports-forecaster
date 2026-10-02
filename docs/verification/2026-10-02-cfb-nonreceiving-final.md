# Exact CFB passing and rushing final-result recovery

The free SportsDataverse 2026 player-box asset was last published before the
October 1 Tulsa–North Texas final. The hosted primary game-log table therefore
had no rows for that event at the October 2 audit. The existing explicit ESPN
recovery accepted receiving totals but classified quarterbacks as unavailable
because it intentionally required receiving columns.

A bounded private bundle archived the exact final summary and the 13 forecast
athletes' game logs. The receiving-only path authenticated and settled 28
forecast rows. The separate passing/rushing parser in this change verifies
seven athletes' exact game-log values against the final box score. Its read-only
hosted preview found 20 additional, still-pending pass/rush forecast rows:
11 false and 9 true, with zero accepted picks. The preview does **not** write
these results. Raw responses, athlete details, and the full bundle remain in
ignored private storage; its SHA-256 is
`6bfa0f4f0c0a24e73ee4dda8e72a11850416a3e9f5c2d2d994c9b54bee757f30`.

## Proof boundary

The parser accepts only the existing version-1 bundle's fixed ESPN final and
exact athlete game-log URLs. It checks response hashes, timestamps, final
regular-season event, league/season/week, Eastern slate date, start time,
teams and score. It requires one matching event entry and uniquely named stat
columns. Passing requires explicit attempts and yards, matching box-score
C/ATT and yards, and matching completions when supplied. Rushing requires
explicit carries and yards matching the box score. The athlete must occur on
one team and have positive attempts; zero yards with positive attempts is
valid. Missing categories, zero attempts, absent box-score corroboration, and
unmatched forecasts stay unresolved. Source contradictions raise an error.

The recovery CLI previews through a read-only hosted snapshot. Applying it
requires `--apply --expected-count N` after reviewing the exact count. The
existing atomic writer locks forecasts, checks immutable payloads and missing
outcomes, compares any primary stat already stored, revalidates settlement
proofs, and checks the write count. This recovery updates outcomes only. It
never adds historical model inputs, changes probabilities or pick gates,
requests paid odds, spends credits, or places bets. The receiving path and its
source contract remain unchanged.

## Verification and limits

Synthetic tests cover a passing/rushing source-proof round trip, explicit zero
yards with positive carries, missing passing box evidence, contradictory final
sources, malformed event stats, market/identity isolation and replay
rejection. Disposable PostgreSQL CI exercises two result types in one atomic
write and checks retained forecast payloads and proof validation. The real
private bundle preview exercised all 13 athletes and 20 proposed outcomes.

The frozen forward market audit still has zero qualifying two-book CFB
selections and reports insufficient evidence. These 20 repeated forecast rows
cannot establish a prospective edge or a win-rate claim. Release and any
production application require reviewed CI and the normal branch-protection
approval path; do not bypass the separately unapproved reserve PR #194.
