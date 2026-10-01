# Individual-pick context diagnostic

`python -m sportsbet.quant.individual_pick_context_audit --output PRIVATE_REPORT.json`

This is a private, read-only diagnostic of existing NFL raw-model paper selections.
It does not collect quotes, write receipts, publish snapshots, change the public
selector, or promote a candidate. Never upload its output to GitHub.

## Evidence boundary

The existing frozen model-selection verifier first authenticates selection identity,
original offer prices, dependencies, deadlines, retained forecast evidence and
settlements. Any invalid source receipt prevents subgroup output. The diagnostic
keeps the originally recorded selection; it cannot substitute a later quote,
market, player or receipt when context is absent.

The current recent-role-v2 verifier independently authenticates the exact forecast's
retained input bundle. Its server receipt must exist by the paper selection's
recording time. Recent form is derived from those validated rows, not today's
mutable game logs. Context coverage includes unavailable inputs and reasons.
Legacy individual-pick-v1 and all frozen model/evaluation implementations remain
unchanged.

## Fixed diagnostic rules

1. Original recorded probability at least 75%.
2. Also last-ten Jeffreys probability at least 75%, latest game at most 30 days old.
3. Also current-role probability at least 75%, at least two current-team/current-season
   games, older history available, and latest observed team matches captured roster team.

Returns use original matching offer prices. Only authenticated results observed by
the audit time count as decisions; missing or future outcomes stay pending. Reports
separate selected, upcoming, pending, decided, wins, games, win rate, return and
recorded/market probabilities. They never label a consensus score a calibrated probability.

These are exploratory subgroups of prospective paper selections, not a separately
preregistered 75% selection experiment. Descriptive game-clustered intervals are
unadjusted for subgroup search. `target_verified` and `promote` stay false. NFL
receiving context does not establish results for NBA or CFB.

## Runtime reproducibility

Run with Linux CPython 3.12 and the locked dependencies. Frozen role-v2 inputs include
compressed bytes: Python 3.12 on Windows writes a different gzip OS byte than Linux.
The diagnostic rejects incompatible runtimes before database access. Do not edit
compressed receipts, normalize their bytes, weaken their hashes, or modify the
frozen verifier to accommodate a local host.

A local WSL environment can run the locked project and keep private results on the
local disk. Supply database credentials through the environment, never shell command
arguments or tracked files. The audit uses one repeatable-read, read-only database
snapshot and prints only completion status.

## Tests

Tests cover real v2 input replay, missing/legacy/tampered/late receipts, unchanged
75% and current-role bounds, source verification, duplicate identities, nonmutation,
original selection retention, authenticated outcome timing and exact-price returns.
