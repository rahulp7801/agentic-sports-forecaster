# Frozen teammate-target-share study: no incremental predictive support

Ran the [October 1 fixed protocol](2026-10-01-nfl-team-target-share-protocol.md)
and its existing [study code](2026-10-01-nfl-team-target-share-study.py) on
October 3 without changing its model, splits, features, penalty, lines, or
selection rule. This is an internal, retrospective **unpriced** study, not a
consumer pick, accepted strategy, or market edge.

The free official nflverse weekly player-stat Parquet assets were
`stats_player_week_2023.parquet` (asset 513240108, SHA-256
`ac776fbd7c9fefdb4069b72304f4c5fa05ae417acd49f6e4e27be14b9d7a4bbc`),
2024 (513240737, `847569d194ca3d96b5efcf91e6eac5e18780fc47568a713fd545a82d29d155c1`),
and 2025 (513243463, `2a461becaa9adb3c93a3074a3a31f1e960162a50163371a2d34e28393b5fff10`).
The official `games.parquet` schedule asset 607460864 had SHA-256
`4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662`.
All downloaded/copied bytes matched their release digests. The three yearly
stat files were concatenated into an ignored local Parquet file with SHA-256
`2e3ff906fd9fdb63a40068c2318a6a2fa235f1af55316063f43fdcb50c0b8bb8`.

The baseline uses the seven already frozen history/workload features. The
challenger adds two pregame features from prior same-team games: the player's
share of team targets and the largest other player's share. Both use the
same 2024 fit examples, fixed L2 penalty 0.1, synthetic research lines,
and 2025 evaluation rows. No outcome from the target game enters a feature.

| Split | Eligible examples | Games | Baseline Brier | Context Brier | Context minus baseline Brier | Game 95% | Player 95% |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024 fit | 3,903 | 223 | — | — | — | — | — |
| Early 2025 selection check | 2,132 | 106 | 0.210726 | 0.210786 | +0.000060 | [-0.000178, 0.000297] | [-0.000207, 0.000326] |
| Late 2025 evaluation | 3,257 | 150 | 0.211215 | 0.211243 | +0.000028 | [-0.000176, 0.000231] | [-0.000174, 0.000230] |

On the evaluation rows, context-minus-baseline log loss was +0.000077;
both game and player 95% intervals also crossed zero. Smaller is better for
both scores. The added shares have **no demonstrated incremental predictive
benefit** on this fixed evaluation. Keep current teammate usage as visible
context and screening evidence. Do not adjust the published probability or
relax qualification to manufacture picks.

The locked-version private aggregate report is ignored at
`.local/team-share-report-locked-20261003.json`, SHA-256
`37cb94299965281511c8adc4361d43a3bac6a169ce94067c1987f0bd49d9a85c`.
It uses numpy 2.5.3, scipy 1.18.1, pandas 3.0.5, polars 1.44.2,
statsmodels 0.15.0 and psycopg 3.3.5. An initial run on slightly different
local numerical versions gave the same conclusion. Reproduce from the
ignored, hash-verified sources with no database or provider request:

```text
python docs/verification/2026-10-01-nfl-team-target-share-study.py \
  --stats PRIVATE_STATS_PLAYER_WEEK_2023_2025.parquet \
  --schedules PRIVATE_GAMES.parquet \
  --report .local/team-share-report-replay.json
```

Limitations: the source snapshots may contain later stat corrections, the
research lines are not historical bookmaker offers, observed participants
do not provide a DNP census, injury state and original pregame source
versions are absent, and no return or market-price comparison is possible.
The [nflverse repository license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)
publishes CC BY 4.0; a [pending upstream-rights clarification](https://github.com/nflverse/nflverse-data/issues/101)
specifically asks about use of these files in a paid analytics product.
No conclusion about those upstream commercial rights is inferred here.


## Commercial-source checkpoint, October 3

The upstream [licensing question #101](https://github.com/nflverse/nflverse-data/issues/101) was closed as `not_planned` on 2026-10-02 with zero comments. It did not answer whether the repository's [CC BY 4.0 notice](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md) covers upstream commercial rights for the weekly player-stat fields used in this research. The source files remain hash-pinned and this study remains private. The closure supplies **no additional commercial permission**. Before offering a paid service that uses or displays those data or derived outputs, obtain an authoritative rights decision or use a source with confirmed suitable rights; do not infer permission from this unanswered issue. This is a product release risk, not a change to the forecast result, model, or source chronology.

The protected CI security jobs still cannot start on the current account. As a local checkpoint on the consolidated private release, installed Gitleaks 8.30.1 scanned the single release commit with full redaction and reported no leaks; `npm audit --omit=dev --audit-level=high` reported zero frontend production dependency vulnerabilities. These checks do not replace the complete hosted CI or resolve the data-rights question.
