# NFL context source replay — October 8, 2026

## Reproduced gap

At private head `27fe35a2db61e637f9853cb4870f1e806b1b2c6a`, the consumer
participation query checked hash shape but did not replay the target stat or
snap-count commitment. Its two real PostgreSQL chronology tests passed using
placeholder `b` hashes, demonstrating that the source check accepted unproved
values. Research history auditing already performed the stronger verification.

The consumer query also read mutable opponent enrichment and could describe
auxiliary NFL categories that the frozen core result hash does not commit.
Those are unsuitable inputs for a source-backed comparison.

## Repair

The new `nfl_participation_evidence.py` reader obtains its target, participant
tenure, relevant snap rows and exact game mapping in **one SQL snapshot**.
Every cutoff, identity and season remains a parameter. Only four committed
metrics—passing/rushing/receiving yards and receptions—can use this comparison.
The existing frozen stat hashes, model probabilities and qualification rules
remain unchanged.

The reader verifies normalized target and snap commitments, matching player
IDs, canonical season/week/game identity, clubs, integer counts and source
chronology. A unique schedule mapping supplies the opponent; mutable stat
enrichment cannot change that relationship. Target games must precede the
decision's game cutoff and source observations must precede its selection
clock. Tenure must be established from a source-proved positive prior game.

Legacy NFL yard hashes remain supported for fields they commit. They cannot
authenticate an uncommitted reception count. The reviewed receiving supplement
still requires its complete manifest, explicit final-source proof, original
game/club mapping and insertion cutoff. Invalid target/tenure proof withholds
the comparison. Missing, ambiguous or damaged per-game participation is
unknown. NFL zero snaps remain unknown because legacy ingestion could fill
null with zero; they do not become invented absence evidence.

New NFL comparisons use aggregate v3 evidence. The public projection withholds
older v2 NFL comparisons while retaining current injury reports, roster proof
and the same model probability. It strips private source rows, tenure receipts
and cutoffs. The NBA v3 repair remains intact. Failures in optional context do
not erase an otherwise recorded forecast or relax its existing eligibility
gate. No production schema migration was added.

Private receipts retain only replay inputs. Offline replay of the original
eight audited cases preserves every aggregate and replays the compact receipts
exactly. Normalized JSON proof payload fell from **261,419 to 204,542 bytes**,
about **21.8%**. This does not change sources, observations or classifications.

## Actual existing-data verification

Two read-only audits used the existing hosted schema
`0039_prediction_record_receipts`, verified read-only transactions and bounded
queries. They ran the pending reader locally; they did not deploy it.

- The initial eight QB/positive-snap teammate history cases all proved. They
  covered one club/subject and 18 distinct subject-games. Their overlapping
  histories contain 91 active and 15 unknown entries, including 32 current
  season entries; the latest sampled game is October 4.
- That first sample was insufficient to support league-wide compatibility.
  A second audit reused its existing club and sampled one case for each of
  the **31 remaining clubs**. All 31 proved, including the source team-code
  conventions. These contain 363 active and 105 unknown entries, including
  107 current-season entries.
- Together, there is at least one successful source-replayed QB/teammate
  history case for **all 32 NFL clubs**. This is a bounded input compatibility
  check, not complete coverage of every player, prop, opponent or injury.
- No current injury status was inferred. These are explicitly labeled history
  audits, not real current injury reports, model forecasts, market offers or
  picks. Repeated histories are not independent prospective performance cases.

Raw source receipts and audit scripts remain ignored and local. The original
eight-case audit SHA-256 is
`174fbf94b9b413498b395889c288bea80dd01eb0add2ef4cb47703bc1f0932e2`.
The read-only audits made **zero source/quote collection requests, zero database
mutations and zero pick publications**. Original receipt timestamps were not
rewritten. The compact replay made no network requests.

## Retained nonparticipation marker audit

A separate read-only audit at **2026-10-08 13:05:48 UTC** examined the
already retained frozen ESPN source bundle. Its 24 final-game rosters contain
65 literal `didNotPlay=true` markers. These responses have no declared
pagination totals; all marker entries have `valid=false`. These facts are
recorded as provider markers, without interpreting the provider's undocumented
validity flag as a verified absence or a played result.

The audit replayed the unchanged raw response/identity commitments, final
regular-season game/date, both event rosters, athlete references and original
post-final receipt chronology through the existing frozen inspector. It also
checked roster competition/team references, unique entry IDs, bounded roster
lengths and unique GSIS/ESPN/PFR bindings. It bound **64 markers**, representing
**62 players and 12 games**; **13 markers** concern the 2026 season. One marker
had no unique complete crosswalk and remains unbound. Expanding the requested
identities for this audit did not rewrite the original frozen bundle or its
originally selected players/results.

One bounded, parameterized read-only query against the existing production
snap table found **no matching player/game snap row for any of the 64 markers**.
Consequently, missing snaps cannot supply the dashboard's absence cohort.
There are zero confirmed absences from this audit, and no target-stat zero,
automatic void, probability adjustment, injury claim or qualified pick was
created. This sample neither proves complete roster coverage nor independently
corroborates the provider's nonparticipation semantics. Historical absence
comparisons need a separate reviewed proof contract retaining the explicit
original final-game entry, exact identity and source chronology; the current
consumer snap reader continues to report these cases as unknown.

The original compressed bundle SHA-256 remains
`8fa1995e608405945c2f1a6289a3ac718f35c9b5845344b0c0d4334d480b8750`.
The local audit receipt SHA-256 is
`b0ee112841172eee64b90caf2987252862d4553b91778cec4f1aa53894fe847d`.
Its raw receipt and audit script stay in ignored local storage. This operation
made zero source/quote collection requests, database mutations, pick
publications or raw evidence uploads. It is an input-gap audit, not new
prospective performance evidence. Frozen final-evidence and consumer proof
regressions passed **81 tests**; application code did not change in this audit.

## Tests and remaining boundaries

- Full backend gate: **2,530 passed**, 128 environment/database skips; seven
  existing mocked NBA/pandas warnings. The final compact-receipt tests were
  added afterward and exercised separately.
- Full frontend suite: **335 passed**; TypeScript and changed-file lint passed.
- Clean full migration chain: **12 passed**.
- PostgreSQL release gate: **148 passed**, with 29 existing SQLAlchemy reflection
  warnings. It includes the genuine source fixtures, source/hash tampering,
  chronology, receiving supplement, source priority, permission repair,
  waitlist provisioning and existing NBA/CFB/tracking tests.
- Final compact receipt checks: **66 source/context tests passed**, then
  **26 receipt/receiving tests passed**, including real PostgreSQL receiving
  behavior and preservation of the supplement manifest/insertion cutoff.
  An initial repeat refused existing fixture roles, as designed; a clean
  task-owned container resolved that test-order issue without rotating roles.
- Cached Bandit passed without downloads. Source/model contracts and all
  frozen research modules remain unchanged.

Database tests use only cached PostgreSQL 16 in the task-owned loopback fixture.
PR #345 remains the existing consolidated private release. Hosted exact-head
CI, required private CodeQL, owner OAuth and protected waitlist verification
still precede production activation. Existing public containment remains.
No production DDL, permission change, merge, deployment, subscription, paid
storage, card, credit purchase, order or bet was introduced. PR #194, the
20/day and 450 rolling limits and staged reserve are unchanged.

## Next evidence checkpoint

The original October 8 capture and publisher remain Ready at **17:00 UTC /
10:00 Pacific** and **17:25 UTC / 10:25 Pacific**. Verify their actual exit codes,
original source/price chronology, all three frozen study receipts and shared
preserved pregame anchor, followed by the local recovery package. Do not create
an after-kickoff replacement for a missed capture.

NFL absence effects remain unestablished where there is no explicit final
nonparticipation source. This repair supplies verified descriptive inputs,
not a causal teammate adjustment or measured alpha. The independent current-form,
recent-history and Questionable-teammate studies retain their existing matching
price, outcome coverage and game/player uncertainty gates. A profitable edge
and a 75% individual pick win rate remain unproved.
