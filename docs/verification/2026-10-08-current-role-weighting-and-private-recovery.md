# Current-form weighting and private evidence recovery

## What the original role model actually did

The unchanged October 3 role pair has 452 selected contracts, 308 source-backed
role forecasts, 303 authenticated binary outcomes and five retained nonbinary
outcomes. There are 15 paired games and 145 players. All original role/market
pairs were within the original five-minute quote window. The original role
evaluator was replayed against the existing authenticated settlement wrapper;
no result, quote or source collection was repeated.

On these **same 303 original pairs**, lower Brier and log loss are better:

| Forecast | Brier | Log loss |
| --- | ---: | ---: |
| Original role, prior strength 20 | 0.275592 | 0.755525 |
| Original embedded prior20 control | 0.274517 | 0.752703 |
| Matching original market midpoint | 0.243873 | 0.680379 |
| Post-result illustrative capped prior | 0.264754 | 0.728818 |

The original role adjustment slightly worsens its prior20 control. Its equal-game
Brier difference versus that control is +0.001028; both original game and player
95% cluster intervals are above zero. Its matching market is also better on
average. This is insufficient evidence for consumer promotion or an edge.

The mechanism is concrete: with three current-club games and 17 older games,
the fixed strength-20 role posterior gives current observations 3/23 weight
(13.04%). The embedded prior20 Jeffreys baseline gives those observations 3/21
weight (14.29%). A fixed 20-observation prior can outweigh even a small older
sample later in the season. The existing role model therefore does not reliably
increase the influence of how the player is performing now.

The single illustrative alternative uses `strength = min(8, older_games + 1)`
and the same older Jeffreys probability. With three current games its weight is
3/11 (27.27%). It was defined **after** the October 4 results were known. On that
slate it reduces error versus the original role and embedded prior20 controls,
but still trails the original market overall. The matching-market game and
player intervals cross zero. All four prop bins and all five nonbinary outcomes
remain in the local exploratory report. No subgroup was selected for promotion.

This is not a comparison with the separately timed stat-only forecast: that
forecast has a different model scope and market observation time. It is also
not an executable price, ROI, causal teammate effect or a 75% win-rate claim.

## Prospective current-form comparison

`kalshi_role_weighting_study.py` introduces the separate frozen protocol
`kalshi-nfl-prospective-role-capped-prior-v1`, starting October 8 at 17:00 UTC.
October 4 cannot enter its validation sample.

The existing one-shot capture freezes `role-weighting.json` immediately after
the original role pair, while **all original selected midpoints are still at
most 300 seconds old**. It requests no new price or source. Exact threshold hit
counts are recovered from, and checked against, both authenticated original
role and prior20 probabilities. Changed counts, probabilities, contract
identity, original midpoint or chronology reject the receipt.

The publisher replays the original source/schedule/stat-only/quote commitment
first, then verifies the role receipt, policy and normalized implementation
hash. A new hash-only role marker is staged alongside the primary and teammate
markers in the **same amended release commit and exact preserved research ref**.
No additional scheduled task, commit or provider request is introduced. Missing
or late receipts cannot be constructed by the scorer after the games.

The new scorer requires the original full-cohort settlement gate and authenticated
venue results, the server-dated private PR push, the original exact preserved
ref and the role marker in that same commit. The earliest published capture owns
the entire fixture before forecasts or results are filtered; later captures
cannot replace missing forecasts or nonbinary results. Original unavailable
contracts, overlaps and result states remain visible.

Its single primary scope is **all original role forecasts**, with Brier/log-loss
comparison against the matching original midpoint, original role20 and embedded
prior20 controls. Predictive support requires complete forecast result coverage,
at least **50 independent paired games**, and favorable game and player intervals
for both proper scores versus all three comparators. Executable edge,
qualification, fills, ROI and CLV remain unproven regardless of that diagnostic.
The primary stat-only, recent-gap and teammate study models and policies remain
unchanged.

Focused verification covers actual current-weight increases, empirical-count
reconstruction across 2–19 current games, old-cohort exclusion, stale quote
rejection, tampered probability/price/policy checks, original gate ordering,
same-commit server anchoring, whole-fixture overlap ownership, unavailable and
nonbinary retention, paired market errors and source-safe launcher resolution.
All 308 retained original role rows also reproduce the formula; that compatibility
check creates zero prospective cases and makes zero network requests.
The complete focused suite passes **138 tests**; its sole warning is the
unused `asyncio_mode` setting with automatic pytest plugins deliberately
disabled. Cached Bandit passed. The original six frozen recent-gap/evaluator
sources are unchanged. The new study binds its own role/model/scorer and direct
chronology/result/remote-anchor dependencies before the first capture.

## Owner-private recovery

With the owner's explicit authorization, `rachitj27` and `fauzanantb` were removed
from the private repository. The collaborator list now contains only
`rahulp7801` (ID 76501505), with no pending invitations. This revokes future
repository access; previously obtained copies cannot be revoked.

The original roster file was recovered from temporary storage only after its
pinned SHA-256 matched
`4792e44d65e6df9b56e39cb4c16d172e08175a2e6a9daf25cfb718b0d0533bbf`.
Original input and pregame receipts were not rewritten or backdated.

An allowlisted archive contains 54 files: the frozen cohort/context inputs,
authenticated settlement wrappers, original role score, explicitly exploratory
weighting results, original roster source and three local replay scripts. Every
archived file was read back against its size and SHA-256 manifest. Redacted
Gitleaks scanned the allowlisted staging tree and decoded compressed source;
neither scan found a secret.

The archive is an **unpublished private draft**, not a deployment or consumer
release. Draft release ID: **406451923**; asset ID: **620836775**; asset name:
`sportsbet-fixed-evidence-20261008.zip`; bytes: **7,751,995**.

Archive SHA-256:
`b1606e951b813c978e8d163cf14a2bd475b814c8fbb44b9b3f4405f737eec865`.
Both GitHub's asset digest and the downloaded remote archive match this hash.
Its recovery manifest records actual recovery time separately from original
source and pregame collection chronology. No Actions artifact, LFS allocation,
paid credit, card use, bet or order was introduced.

## Exact next checkpoint and remaining release gates

At **October 8, 17:25 UTC / 10:25 AM Pacific**, verify both scheduled task exits,
the original source/week/receiving/schedule receipts, timely `role-weighting.json`,
teammate receipt, all three hash-only markers in the same commit, exact preserved
private ref and server push before the first selected kickoff. At **October 10,
17:25 UTC**, check the fresh Saturday capture and within-48-hour Sunday teammate
coverage. No missed pregame capture may be backfilled. The resulting commitment
will provide the exact full-cohort first eligible settlement time.

Read-only production verification still shows the containment firewall active
with unchanged unrelated-settings digest. Production `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET` and `WAITLIST_DATABASE_URL` are missing/ambiguous. The
reviewed release remains gated by strict required checks; the account billing
gate and missing private CodeQL capability have not been bypassed. No merge or
production deployment is claimed, and the owner dashboard remains contained
until the protected OAuth release succeeds.
