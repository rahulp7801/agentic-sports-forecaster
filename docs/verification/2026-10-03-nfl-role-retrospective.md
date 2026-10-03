# NFL current-role formula: retrospective quoted-universe check

This is a **development diagnostic**, not an untouched backtest or a market
edge. The October 2 frozen Kalshi cohort supplies 399 uniquely identified
player/prop pairs (18 of 417 contracts lacked a unique crosswalk identity).
Historical examples are only those players and prop types, which introduces
survivorship selection. There are no historical Kalshi or sportsbook offers
for these examples. The line is `floor(median(last 10 prior played stats)) +
0.5`, a synthetic half-point research threshold selected before each target
game, never its actual result. The historical archives were released or
corrected in 2026, after the 2025 target games. This checks a formula's
retrospective probability calibration, not historical tradability.

The script [2026-10-03-nfl-role-retrospective.py](2026-10-03-nfl-role-retrospective.py)
replays the exact 417-contract market selection and checks all six pinned
nflverse source SHA-256 values, release times relative to the October 2
capture, and the unique pinned GSIS/PFR crosswalk. For each target player
game it constructs the last 20 **strictly prior** positive-offensive-snap
games, requires the same two-current-team-game role rule as the frozen
shadow, and checks recent team usage. It evaluates the frozen role formula
against a plain Jeffreys `(prior-20 overs + 0.5) / 21` estimate on identical
player/game/line outcomes. A missing target stat row is scored zero only with
positive offensive snaps; a separate sensitivity excludes those rows.

The output contains aggregate counts and scores only. Within each prop and
year, each game receives equal weight. Two thousand seeded whole-game and
whole-player bootstrap resamples give separate descriptive percentile
intervals for role-minus-baseline score. Lower Brier/log loss is better;
**positive** difference favors the plain prior-20 baseline. These intervals
are not adjusted for inspecting four props or for the quoted-universe and
postgame-source selection.

| 2025 synthetic market | Rows | Games | Players | Role minus baseline Brier | Game 95% | Player 95% |
|---|---:|---:|---:|---:|---:|---:|
| Passing yards | 174 | 140 | 20 | -0.00025 | [-0.00544, 0.00493] | [-0.00653, 0.00708] |
| Rushing yards | 482 | 210 | 51 | +0.00441 | [0.00061, 0.00831] | [0.00037, 0.00878] |
| Receiving yards | 1,114 | 221 | 110 | +0.00278 | [0.00034, 0.00531] | [0.00051, 0.00508] |
| Receptions | 939 | 218 | 93 | +0.00394 | [0.00150, 0.00639] | [0.00132, 0.00692] |

The receiving/rushing differences are also positive when target-game zeroes
inferred from snaps are excluded: +0.00439 rushing (481 rows), +0.00249
receiving yards (1,076), and +0.00362 receptions (916); both cluster
intervals remain above zero for each. Log loss has the same direction.
The 2026 check has at most 16 games per prop (13 for passing); its small
role-minus-baseline differences are not decisive. Of 6,362 positive-snap
player/prop target games attempted, 2,839 lacked 20 prior games, 551 lacked
the current-team role, and 2,972 were scored. Sixty-five scored target
zeroes were backed only by positive offensive snaps.

This result **does not support promoting the current-role formula over the
simple prior-20 baseline**. The current role shadow and teammate usage in
the frozen October 3 receipt remain unchanged. Teammate share is currently
descriptive context, not a validated probability adjustment. A future
challenger needs its own pregame receipt, matched current market prices,
authenticated settlements, enough independent games, and a separately
frozen decision policy before any consumer edge claim.

The private aggregate report is ignored at
`.local/nfl-role-retrospective-audit.json` (SHA-256
`3f5133cd1677364623f35446bf618e81a7221c18abae682de4086f4d9c4e6059`).
Reproduce from the retained ignored Oct 2 market/source backup, without any
provider call:

```text
python docs/verification/2026-10-03-nfl-role-retrospective.py \
  --root PRIVATE_KALSHI_BACKUP_WITH_COHORT_MARKET_ARCHIVE_AND_SOURCES \
  --output .local/nfl-role-retrospective-audit.json
```
