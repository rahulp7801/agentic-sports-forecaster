# NFL recent-season 75% stress test: completed 2026 games

This is a separate **unpriced retrospective** replay. It keeps the previously
selected stat-only correction coefficients fixed and uses strictly prior played
games to form each example. The model, current 70 Kalshi paper decisions,
11 original high-probability decisions, eight receptions-only paper decisions,
consumer probabilities and qualification thresholds do not change. No quote,
API credit, order, bet or live result was requested.

The [offline script](2026-10-04-nfl-stat-only-recent-2026-replay.py) checks the
pinned 2024-26 player statistics and offense-snap assets against the existing
source manifest, plus the player crosswalk, full schedule, original selected
model report, and exact October 3 quote-pair file (SHA-256
`8df6075f9794837f9c99772cf70d5dbdfb7954a07421ebfda0345494637e9acb`).
It restricts target games to completed 2026 regular-season games
with scheduled dates from September 1 through **before October 4**. Every
target requires a positive offense snap; a missing stat row is assumed zero
only in the separate snap-backed sensitivity. The explicit-target-stat slice
requires a recorded target stat. Lines are synthetic half-point lines above
the median of the player's last ten strictly prior played games, with at least
2.5 receptions or 19.5 receiving yards. The sample retains only player/prop
identities present in the later October 3 quote pair. It has no historical
matching bookmaker line, price, fill, fee, injury report as of target time, or
closing-line evidence.

| 2026 corrected-history slice, model NO p >= 75% | Examples | Games | NO wins | Row win rate | Equal-game rate | Mean model NO | Descriptive game-cluster 95% |
|---|---:|---:|---:|---:|---:|---:|---|
| Receptions, snap-backed zeros | 60 | 32 | 42 | 70.00% | 67.24% | 82.43% | 52.08%-82.40% |
| Receptions, explicit target stat | 56 | 31 | 38 | 67.86% | 65.11% | 82.14% | 49.52%-80.70% |
| Receiving yards, snap-backed zeros | 32 | 21 | 22 | 68.75% | 63.89% | 80.11% | 43.70%-84.08% |

For comparison, the same exploratory rule on late-2025 corrected-history
receptions examples produced 91/112 (81.25%) across 77 games. The recent
receptions rate is **below 75%** and far below the model's average 82.43%
probability. Within the 60 high-confidence 2026 examples, the model-minus-
prior-20 Brier difference is +0.00336 (game-cluster 95%
[-0.02908,+0.03580]), so it shows no advantage over the simple recent-history
probability baseline. On all 223 2026 receptions examples from 47 games, the
model-minus-matched-20-to-40-history Brier difference is -0.01087 but its game
interval [-0.02460,+0.00285] also crosses zero. The narrow confidence slice
was chosen after examining prior outcomes. Both years use later 2026
quoted-player identities, and each source was published after its target
games. These descriptive intervals do not correct for repeated research,
selection or correlated picks. This is evidence of a **calibration risk**, not
a clean untouched holdout, a priced backtest, or proof that the strategy loses
or wins at current market prices.

The ignored aggregate report is
`.local/nfl-stat-only-recent-2026-verified-20261004.json`, SHA-256
`0bd9f4f363e09f53a20c5d96ccb42b141395d3fc9985b021b5de375130f5f9d1`.
Two offline runs produced identical bytes. The script emits only aggregate
counts; no player or contract rows are tracked. Replay to a new ignored path:

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-nfl-stat-only-recent-2026-replay.py `
  --output .local/nfl-stat-only-recent-2026-my-replay.json
```

## Exploratory current-role diagnosis

A separate `--recent-role-diagnostic` replay preserves the base report **byte
identical** and writes only aggregate post hoc bins to a different ignored
path. It divides the same 60 model-NO >=75% receptions examples by the
existing pregame `recent_mean_delta` feature: last-five mean at least 0.5
historical standard deviations above the prior 20-40 game mean, within
(-0.5,+0.5), or at least 0.5 below. This feature is already an input to the
frozen model; the binning does not create new model features.

| Recent mean relative to history | Rows | Distinct games within bin | NO wins | Row win rate | Mean model NO |
|---|---:|---:|---:|---:|---:|
| Rising | 17 | 16 | 11 | 64.71% | 83.85% |
| Stable | 35 | 23 | 26 | 74.29% | 82.33% |
| Falling | 8 | 8 | 5 | 62.50% | 79.90% |

The bins sum to the original 60 rows and 42 wins; their game counts overlap
because one game can have players in multiple bins. Even the stable bin has a
point win rate below 75% and below the model's mean. These small, post hoc,
unpriced bins do **not** identify a validated role-based exclusion rule. They
suggest the 2026 overconfidence is not confined to rising roles. No live
context gate or candidate set changes.

The ignored separate aggregate diagnostic SHA-256 is
`07d5c7845328a0bb4d4605733bf9b06ea77213b642f423656ad4abe7cde74a72`;
two offline runs matched exactly. Reproduce with a fresh ignored path:

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-nfl-stat-only-recent-2026-replay.py `
  --recent-role-diagnostic `
  --output .local/nfl-stat-only-recent-2026-role-my-replay.json
```

This recent-season failure is a reason to withhold any 75% consumer claim or
model promotion. The next independent test remains the fixed October 4
prospective cohort with exact pregame asks, scheduled later free prelock checks,
and venue-authenticated results only after October 6 06:15 UTC. Even a
positive paper margin there would need more independent games, price
persistence, fills and fees before it could establish an executable edge.

## Post hoc last-played-game freshness diagnosis

An additional `--freshness-diagnostic` run retains the original high-model-NO
selection and denominator. It bins examples by the number of calendar days from
the most recent **verified prior played game** to the target game. The 1-10 day
bin represents a normal recent NFL interval; 11-30 and over-30 days are
separate. The age is derived from the same hash-pinned schedule and positive
snap-backed history as the base replay. It does not use a later player profile
to decide what team or game was current.

| Fixed 2026 NO slice | Last game | Rows | Games within bin | NO wins | Row win rate | Mean model NO |
|---|---|---:|---:|---:|---:|---:|
| Receptions, snap-backed zeros | 1-10 days | 26 | 20 | 15 | 57.69% | 82.57% |
| Receptions, snap-backed zeros | 11-30 days | 3 | 3 | 3 | 100.00% | 82.11% |
| Receptions, snap-backed zeros | >30 days | 31 | 11 | 24 | 77.42% | 82.37% |
| Receiving yards, snap-backed zeros | 1-10 days | 8 | 8 | 4 | 50.00% | 78.27% |
| Receiving yards, snap-backed zeros | 11-30 days | 1 | 1 | 1 | 100.00% | 80.40% |
| Receiving yards, snap-backed zeros | >30 days | 23 | 12 | 17 | 73.91% | 81.21% |

These rows sum to the original 60 receptions/42 wins and 32 receiving-yard/22
wins. The explicit-target-stat receptions sensitivity is 13/24 within 10 days,
3/3 at 11-30 days, and 22/29 after 30 days; its original 38/56 wins remain
unchanged. Game counts across bins overlap when different players from the same
game occupy different bins. The short-age point rates are worse, so a simple
30-day freshness cutoff is **not** supported as a 75% win-rate repair.
Offseason first games can naturally have a >30-day prior interval. This is
post hoc, unpriced, dependent on later published source bytes and a later
quoted-player universe; it cannot promote, disqualify, or retrospectively
reprice a consumer pick. The frozen October 4 70/11/8 paper decisions and
live model remain unchanged.

Two offline runs emitted byte-identical ignored reports, SHA-256
`79d43cdbb0550b946922e5221b6cfeda2abf794b6855e54c20d512f77548a75d`.
The base report replayed under this optional-diagnostic implementation to its original SHA-256
`0bd9f4f363e09f53a20c5d96ccb42b141395d3fc9985b021b5de375130f5f9d1`.
Reproduce without provider access:

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-nfl-stat-only-recent-2026-replay.py `
  --freshness-diagnostic `
  --output .local/nfl-stat-only-recent-2026-freshness-my-replay.json
```

## Existing lower-tail correction on completed 2026 games

A separate `--tail-calibration-diagnostic` applies the **already frozen 2025
selection-bin offsets** from the [pregame calibration receipt](2026-10-04-kalshi-stat-only-tail-calibration.md)
to the fixed original model-NO >=75% examples in the same unpriced 2026 replay.
It never reselects an example after adjusting probability. Model Over values
outside the predeclared 0.1-0.2 and 0.2-0.3 bands stay explicitly unsupported;
all original high-confidence examples remain in the reported denominator.
The source manifest, later quoted-player universe, synthetic historical lines,
and postgame-source limitations above still apply. The 2026 outcomes were
already inspected, so these are post hoc diagnostics, not independent model
validation or a backtest at matching prices.

| Fixed original 2026 NO slice | Original examples | Offset-covered | Covered NO wins | Covered mean NO before -> after | Corrected still >=75% | Corrected minus original Brier, equal-game | Descriptive game 95% |
|---|---:|---:|---:|---:|---:|---:|---|
| Receptions, snap-backed zeroes | 60 | 55 | 39 | 81.61% -> 78.54% | 39/55 | -0.00889 | [-0.01882, +0.00105] |
| Receptions, explicit target stat | 56 | 53 | 37 | 81.59% -> 78.52% | 37/53 | -0.00951 | [-0.01970, +0.00068] |
| Receiving yards | 32 | 32 | 22 | 80.45% -> 77.37% | 29/32 | -0.00698 | [-0.02171, +0.00775] |

Five receptions examples lack a predeclared correction band (three in the
explicit-stat sensitivity). Among the 55 covered receptions examples, the
observed NO rate is **39/55 = 70.91%**, still below the corrected 78.54% mean.
The corrected-minus-prior-20 Brier difference there is -0.00489, with a game
interval [-0.03588, +0.02609]. All displayed correction and baseline intervals
cross zero. The correction helps the descriptive point score but is not a
supported improvement over either the original model or the recent-history
baseline, and it does not establish the requested 75% individual-pick win rate.
The original October 4 70/11/8 prospective cohorts and consumer model remain
unchanged.

The original aggregate replay stayed **byte identical** at SHA-256
`0bd9f4f363e09f53a20c5d96ccb42b141395d3fc9985b021b5de375130f5f9d1`.
Two separate diagnostic runs produced identical ignored aggregate bytes,
SHA-256 `0cc95b44b69e89cb25ee61510b50163ae38e293405c3f40993f59c912960c16b`.
Reproduce with existing files only:

```powershell
$env:PYTHONPATH='src'
.\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-04-nfl-stat-only-recent-2026-replay.py `
  --tail-calibration-diagnostic `
  --output .local/nfl-stat-only-recent-2026-tail-calibration-my-replay.json
```

This script requests no source, market price, result, API credit, order or bet.
The next independent test remains the already fixed prospective October 4
paper slate, followed by additional precommitted slates before any model
promotion or repeatable edge claim.
