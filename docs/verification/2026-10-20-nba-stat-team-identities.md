# NBA stat team identities

## Source contract

The free official ESPN NBA team directory was observed at
`2026-10-20T06:11:44.209157+00:00`:

<https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams>

The response contained 30 distinct team identities, with SHA-256
`9133e21f5de866c269df1d9e6e49bf20cf84b9e856313cabfbdb4e1845895e99`.
The existing pinned `nba-api` 1.11.4 static table provided 29 unique exact
full-name joins. ESPN's `LA Clippers` name did not exactly match that table and
was not promoted through a fuzzy match. The first audit stopped on that
unmatched name; a corrected audit retained individual exact joins. Two free
team-metadata requests were made; no market quotes were collected.

The additional exact pairs are:

| ESPN team ID | Exact team name | ESPN abbreviation | NBA team ID | NBA abbreviation |
| --- | --- | --- | --- | --- |
| 9 | Golden State Warriors | GS | 1610612744 | GSW |
| 3 | New Orleans Pelicans | NO | 1610612740 | NOP |
| 18 | New York Knicks | NY | 1610612752 | NYK |
| 24 | San Antonio Spurs | SA | 1610612759 | SAS |
| 27 | Washington Wizards | WSH | 1610612764 | WAS |

This directory establishes team identity pairs, not a particular game's result
or the reason any earlier settlement remained pending.

## Compatibility and write boundaries

Schedule identity version 4 requires NBA, an exact same-side abbreviation/name
pair from this table, and at least one of these five additional aliases. It also
handles the previously verified `UTAH` / `Utah Jazz` to `UTA` mapping in a game
involving another new alias. Raw source abbreviations and names remain in the
proof; only the stat comparison uses canonical abbreviations. Unknown aliases,
wrong names, another sport, noninteger versions and duplicate canonical teams
are rejected.

Version 2 remains the default. Version 3 retains its Utah-only interpretation;
Utah-only new settlements continue to use version 3. Already verified version 3
and version 4 results retain their original identity version on recheck. A fresh
versioned result requires all six raw settlement fields to be SQL NULL. No
version 1/2/3 result is upgraded to version 4, and no retained live result can be
downgraded through the legacy or manual writer route.

The live writer uses a fixed parameterized compare-and-set for all six raw
settlement fields, including partially populated legacy state. Null flags are
bound values and work in SQLite and PostgreSQL. A concurrent state change raises
and rolls back the entire call. Legacy result validation and ordinary legacy
writes remain available on legacy records; the frozen ledger itself is unchanged.
The new version 4 reader explicitly rejects a naive settlement observation
datetime. Existing stat provenance validation already rejects negative NBA stats.

The original `ledger.py` retains SHA-256
`e33611de7f85c376b2967f3d1f1bf4a02e80ce093d85c7a1182d29b8799fe2b1`.
Frozen readers still reject versions 3 and 4. No frozen model, study version,
dependency pin, forecast, source receipt, threshold or original evidence is
changed. The live report identifies `live-settlement-v4`; inherited NBA
source-time admission, quote validation, risk and credit limits are unchanged.

## Verification scope

Synthetic regressions cover all five aliases on both sides, Utah hybrids,
source/stat identity and chronology tampering, same-version corrections,
legacy/frozen reader isolation, downgrade rejection, raw NULL guards and both
directions of a concurrent legacy/live write race with transaction rollback.
The real PostgreSQL settlement test includes GS/GSW version 4 alongside existing
version 2 and Utah version 3, including a nonempty recheck and genuine correction.
Required full Linux CI, security, CodeQL and PostgreSQL gates must pass on the
reviewed commit before merge.

These fixture results establish no authenticated live outcome or betting edge.
Actual recovery requires an ordinary daily run with successful history refresh,
verified final-stat evidence and completed source-matching database receipts.
