# Opponent receptions context: small, unpriced historical signal

Ran the [predeclared protocol](2026-10-03-nfl-opponent-receptions-protocol.md)
(SHA-256 `cad6dc744862777ff0cfa059e341572ac4295024a491e5bb9ef31ec05b2ab928`)
with the [offline study script](2026-10-03-nfl-opponent-receptions-study.py)
(SHA-256 `56e9d4a3c7702534ef2cb0438b05a9ae858af79d802c956bbebcc89216170f4`).
The retained 2023–2025 NFL weekly stats and exact schedules had SHA-256
`2e3ff906fd9fdb63a40068c2318a6a2fa235f1af55316063f43fdcb50c0b8bb8`
and `4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662`.
No network, database, paid API, or current quote collection was used.

The challenger adds one pregame scalar: mean receptions allowed by the
upcoming opponent over its latest three to five completed current-season
games. Both models were fit on identical 2024 examples with the same fixed
L2 penalty. Lower scores are better. The paired interval is based on game
or player clusters, respectively.

| Split | Examples | Games | Baseline Brier | Opponent Brier | Difference | Game 95% | Player 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Early 2025 | 1,626 | 74 | 0.208964 | 0.208145 | -0.000819 | [-0.001349, -0.000289] | [-0.001334, -0.000305] |
| Late 2025 | 3,333 | 150 | 0.210282 | 0.209988 | -0.000294 | [-0.000651, +0.000063] | [-0.000648, +0.000060] |

The late-2025 log-loss difference was -0.000751; its game 95% interval
[-0.001568, +0.000066] and player 95% interval [-0.001550, +0.000049]
also cross zero. The fitted opponent coefficient is positive (+0.03583
per standardized feature unit), but the late-period improvement is too
small and uncertain to justify a production probability change. Early-2025
coverage is 1,626 of 2,636 otherwise eligible examples because opponents
had fewer than three current-season games; all 3,333 late examples were
covered. The private aggregate report is ignored at
`.local/nfl-opponent-receptions-report-20261003.json`, SHA-256
`5bf84c699646867b1f7d9904db485296939980c96c483a86f0b7c34279642252`.

This is a chronological retrospective on synthetic lines, with historical
source snapshots that may contain later stat corrections and an observed-
participant census. Earlier 2025 outcomes for other ideas had been inspected.
There are no matching historical executable asks, fills, fees, or prospective
settlements. This does not demonstrate a market edge, a 75% pick win rate, or
consumer-ready qualification. Keep the production model and frozen October
research decisions unchanged. A future challenger would need a fresh
pregame receipt and matched-price results across independent games before
promotion.

Reproduce entirely offline:

```text
python docs/verification/2026-10-03-nfl-opponent-receptions-study.py \
  --stats PRIVATE_STATS_PLAYER_WEEK_2023_2025.parquet \
  --schedules PRIVATE_GAMES.parquet \
  --report .local/nfl-opponent-receptions-replay.json
```
