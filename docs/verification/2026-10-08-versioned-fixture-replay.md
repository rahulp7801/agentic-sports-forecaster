# Versioned repair of the October 8 prospective fixture replay

## Actual scheduled failure

The original local collector ran at October 8 17:00:01 UTC and exited 0. It
completed its source/model/quote inputs and original commitment by 17:01 UTC.
The companion publisher ran at 17:25:01 UTC and exited 1, leaving no teammate
study receipt, remote anchor or local recovery archive. No collector was
restarted and no new quote request was made.

An offline reproduction passed the original model/history, receiving source,
price decision, recent-gap receipt and capped-role receipt checks, then raised
`KeyError: details` in the independent-series fixture mapper. Every one of the
15 selected games has the required details inside the authenticated `milestone`
object. The mapper incorrectly indexed the outer source envelope. The existing
series/study tests mocked this mapper, so they did not exercise the actual
archive structure. The earlier source schema audit did not cover this envelope.

## Explicitly versioned correction

The original v1 series, recent-gap, capped-role and teammate-study files remain
byte-for-byte unchanged. Existing captured receipts, candidate membership,
probabilities, market prices, source observations, model artifacts and cutoffs
are preserved. The actual capture remains 234 original market contracts, 188
original role forecasts, 80 stat-only forecasts and **47 paper candidates in
15 fixtures**. Its original fixed recent-gap groups remain **19 uplift / 28
other**; all 188 capped-role forecasts retain their original capture receipt.
These are research records, not qualified consumer picks or verified outcomes.

- The separate `kalshi_stat_only_next_series_v2.py` reads each selected game's
  nested milestone, using the unchanged strict fixture-key verifier first.
  Duplicate identities, ambiguous fixtures, changed start times and same-team
  fixtures still reject. No game or candidate is dropped to make replay succeed.
- Separate v2 recent-gap/role evaluation modules delegate original receipt
  validation to their frozen v1 implementations. They preserve the existing
  ownership, matching-price, complete-result, 50-game and game/player Brier and
  log-loss rules, while naming and hashing the corrected evaluation explicitly.
  Their manifests/report protocols are distinct from the frozen v1 receipts.
- The separate teammate study v2 preserves the original membership and support
  policy, records its actual later pregame preparation time and binds the v2
  source graph plus the frozen helpers. Its private hash-only marker has a
  distinct `next-nfl-context-v2-<stamp>-anchor.json` name. It does not backdate a
  receipt or pretend the scheduled v1 publisher succeeded.
- The existing publisher now prepares the versioned study with the corrected
  mapper. The launcher admits the explicitly named v2 offline commands; no task,
  trigger, collection quota, staged reserve or provider request is added.

This versioned implementation correction was prepared before the original first
kickoff, October 9 00:15 UTC. It is not a post-result change to selection or a
consumer model promotion. Frozen v1 evaluation reports must not be silently
relabelled or mixed with v2 reports. The original declared policy still governs
whether any later paired result supports a probability improvement.

## Verification before publication

The corrected map reproduces exactly the original strict verifier's entire
15-fixture set. A second actual offline publisher dry-run passed all original
source/model/receipt checks and versioned context preparation, with zero network
reads or original-file writes. The initial affected publisher, source launcher,
role/recent/context/series and local-recovery suite passed **176 tests**.
Additional v2 ownership/scoring/CLI verification is recorded below once complete.
No frontend/runtime/schema source changed; no additional dashboard build or
production acceptance is claimed.

A local original-byte manifest retains all **25 original files / 15,622,152
bytes**, including every source/context asset and original research receipt.
Detailed raw files, manifest and offline diagnostic scripts remain ignored and
local. Only aggregate findings and commitment hashes enter the private review.

## Original evidence checkpoints

The first selected kickoff remains **October 9 00:15 UTC**. A recovered hash
publication must verify GitHub's actual server push before that time; local file
modification clocks or the original scheduled-task time are not substitutes.
All three study receipts and markers must agree in the preserved private commit.
The recovery package must report `local_verified`, full hash/readback verification
and `remote_backed_up: false`, or an explicit local failure.

The original entire cohort's first eligible settlement remains **October 13
06:15 UTC** (six hours after the latest selected kickoff). Do not collect early
partial results or backfill prices to replace this gate. The next already
scheduled capture/publisher remains October 10 17:00/17:25 UTC. The Saturday
Questionable-context window can qualify fixtures that were outside Thursday's
unchanged 48-hour context window; later coverage cannot replace an earlier
eligible fixture owner.

The account CI refusal, required private CodeQL, missing owner OAuth and protected
waitlist provisioning still govern production deployment. Existing dashboard
containment remains active. No edge, 75% win rate, causal teammate adjustment,
execution, ROI, CLV, spending or production activation is claimed.

The final v2-specific suite passes **26 tests**, including the actual nested
source envelope, contradictory outer fields, all original fixture rejection
cases, frozen receipt delegates, earliest-owner/missing-price/nonbinary coverage,
50-game and both-comparator/cluster support rules, no promotion, and the CLI's
original full-cohort result-read gate. Existing controlled policy regression
inputs are reused against the new report paths; those scoring cases still mock
sources/results and are not real performance evidence. The actual 15-fixture map
and complete saved-input dry-run are separate real-input checks. Cached pinned
Bandit passes all four versioned modules, publisher and source launcher.
