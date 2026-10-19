# Utah settlement identity

## Supported source contract

ESPN's NBA team endpoint for team `26` reports the exact pair `UTAH` / `Utah Jazz`:

<https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/26>

The existing free metadata observation was made at
`2026-10-19T19:52:19.223169+00:00`. Its response SHA-256 was
`1493560fea5e6136f08855831b8d3bd388d12761f771000952f0c2532d1a4476`.
This work reuses that observation and makes no additional provider request.

The pinned `nba-api` version `1.11.4` contains one static `Utah Jazz` entry:
NBA team `1610612762`, abbreviation `UTA`. The installed table matched the
distribution's recorded hash. NBA stat ingestion stores canonical abbreviations
in three-character columns. The raw ESPN abbreviation therefore cannot be used
as the canonical NBA stat identity.

## Compatibility boundary

The existing version 2 schedule identity contract rejects `UTAH`. Changing that
contract would also change how retained settlement proofs are reproduced.

The new version 3 contract supports only NBA and translates the exact same-side
`UTAH` / `Utah Jazz` pair to `UTA` for stat comparison. It retains the original
schedule abbreviation, name and source clocks in the proof. Unknown four-letter
abbreviations, a wrong Utah name, another sport and duplicate canonical teams
remain rejected. No other NBA aliases are added.

Only a fresh result with all six original settlement fields SQL `NULL` can first use
version 3. An independently verified version 3 result can use its existing
contract when rechecked. Existing version 1 and version 2 proofs keep their
original interpretation; this is not a proof migration. Raw nonempty malformed
settlement fields must also prevent treating a record as fresh. The selected
contract remains part of the stat cache scope and the generated proof. The write
boundary checks the retained state again and conditionally updates that same
state, so a concurrent legacy result cannot be overwritten by the new contract.

All player, game, stat provenance, source and record hash, finality, observed-time
and outcome checks remain required. Profile roster joins continue to use the raw
ESPN `UTAH` identity introduced in PR #374.

## Verification scope

Synthetic regression tests cover new home and away Utah settlements, rejected
identities, proof tampering and legacy proof preservation. They exercise temporary
local ledgers, without reading original research evidence or making provider
requests. Required Linux CI, PostgreSQL integration and CodeQL must pass on the
reviewed commit before merging.

This change does not establish a new authenticated live result, admit a research
cohort, alter a frozen model or evaluation version, or establish a betting edge.
Live recovery requires a later ordinary daily run with successful history refresh
and independently verified settlement evidence.
