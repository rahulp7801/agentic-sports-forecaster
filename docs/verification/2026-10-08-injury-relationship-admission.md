# Injury-report relationships, positions and units must match

## Reproduced admission failure

The consumer sanitizer accepted a structured injury report whose team equaled
the captured subject club but whose relationship was `opponent`. A local
reproduction used a KC subject, a retained LV opponent and a KC `Out` report
labeled `opponent` / `defense`. The projected record returned `gated: false`
and unchanged model probability 0.65. This was a malformed-fixture reproduction;
no matching production pick or real outcome is claimed.

The risk screen intentionally distinguishes acute offensive teammate absences
from opposing defender reports. Accepting contradictory labels let the former
take the latter's admission path. Structurally valid strings and source hashes
did not establish consistent club relationships.

## Implemented consumer boundary

Structured teammate reports must name the captured subject team and the
producer's `offense` unit. Structured opponent reports must name a different
team and the `defense` unit; when the capture retains its opponent team, the
report must match that exact team. Contradictions withhold the observed
availability block and use the existing `availability_unavailable` gate.
The saved forecast probability remains unchanged and suggested exposure is zero.

The actual suggested-pick selector and fallback watchlist both reject these
contradictory records, including after repeat projection. Coherent opposing
defender reports, questionable offensive teammates and acute offensive teammate
absences retain their existing decisions. Older captures without opponent
coverage keep that coverage unknown; their own club still cannot be labeled
an opponent. Older unstructured acute teammate reports retain their existing
blocker behavior. Stored source records are not rewritten.

The existing participation-split test previously expected observed availability
for two contradictory parent reports. Those cases move to explicit fail-closed
regressions; harmless split/report mismatches still withhold only the descriptive
split. No source, model, prospective study, qualification threshold, owner
authentication policy, reserve or credit cap changes.

## Producer position and unknown-role correction

A further baseline reproduction found six producer failures: whitespace in NBA,
NFL and CFB position labels removed acute teammate reports; an unknown NFL role
was dropped before eligibility reconciliation; and NBA reports could fall through
to football unit classifications. The consumer also accepted an unsupported
position paired with a structurally valid `defense` unit in all three sports.
These are synthetic regression fixtures, not observed production picks.

The producer trims and normalizes position labels and uses the basketball table
exclusively for NBA. For all three sports, an acute same-club teammate whose unit
is unknown remains an unstructured availability blocker. No unit or relationship
is invented. Known NFL defensive roles and K/P/LS retain their existing exclusion;
the existing conservative CFB unknown-role behavior remains. The scanner still
screens the complete collection before trimming the public explanation to eight
reports. No statistical adjustment or frozen evaluation dependency changes.

The consumer now checks that each structured position supports its claimed unit
for that sport. Unsupported structured roles withhold observed availability and
cannot enter suggested picks or the fallback watchlist. Legacy unstructured
acute reports keep their blocker behavior; saved probabilities remain unchanged.

## Verification

The baseline reproduction establishes the previous admission failure. Nine new
cross-sport tests exercise the current NBA/NFL/CFB model and history-policy paths,
club/unit contradictions, valid controls, legacy missing coverage, nonmutation,
repeat projection and actual suggested-pick/watchlist exclusion. The focused
context/sanitizer run passed 64 tests; the complete frontend suite passed
**332 tests** in 44.97 seconds with no failures, skips or cancellations.
The existing Node module-type warnings remain informational.
TypeScript, changed-file ESLint and the local production Webpack build passed.

The position correction adds 13 producer regressions and three cross-sport
consumer regressions. Before the producer fix, six selected cases failed and
seven passed; each new consumer test failed before its fix. Afterward, the
complete frontend suite passed **335 tests** with no failures, skips or
cancellations. The backend context, availability, scanner reliability, scanner
timing and NBA integration suites passed **184 tests** in 373.58 seconds with
the async plugin enabled. Cached Bandit passed for the changed producer.
TypeScript, changed-file ESLint and the local production Webpack build also
passed after this correction. The redacted staged secret scan found no leaks.
The private remote still retains both original prelock research branches at
their original commits; these changes do not touch frozen quant sources.

The change stays in the consolidated owner-only private release review.
Future raw evidence stays local. This correction creates no new observations
or demonstrated market edge. Protected CI/CodeQL, owner OAuth and waitlist
configuration still govern production activation; privacy containment remains
active until the reviewed owner-auth release verifies.
