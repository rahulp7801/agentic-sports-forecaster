# NFL opponent receptions context: fixed retrospective test

This is one research challenger to the existing seven-feature NFL receptions
history correction, prompted by the need for a measurable matchup effect. It
is fixed before inspecting this challenger's score. Earlier 2025 research
outcomes for other features were already inspected; the evaluation below is
temporal, not a pristine independent holdout.

Use the same retained, hash-verified 2023–2025 nflverse regular-season weekly
player stats and exact `games.parquet` schedules as the October 1 teammate
study. Keep unique player/game observations with nonnegative targets and
receptions and matching scheduled season/week/team. Use the existing
`history_tuning.build_examples` receptions examples, observed-player census,
20–40 prior games, five-game target workload floor of 2, and prior-ten-game
25th/50th/75th synthetic half-point lines. Exclude duplicate player/game
rows rather than choose one.

For each scheduled game and defense team, sum the *other* team's recorded
player receptions in that game. A candidate target game's feature is the
arithmetic mean of receptions that its upcoming opponent conceded over its
latest five completed games **in the target season**, all strictly before
the target date. Require at least three such games, positive recorded totals
for both teams in each source game, and the latest source game at most 35
days old. Never include a target-game stat, same-day game, or future game.
Do not fill missing participants or stat corrections with zero. The feature
is a single raw count of opponent receptions allowed per game, not a label
from the target game's result.

Fit one offset logistic challenger using the seven existing features plus
that one scalar. Fit the baseline with exactly the seven existing features
on the same feature-eligible rows. Both use fixed L2=0.1 and 2024 fit games;
no tuning by validation score. The existing early-2025 selection partition
and late-2025 evaluation partition are reported as fixed chronological
checks. Compare game-balanced Brier and log loss, paired candidate-minus-
baseline differences, and game/player-clustered 95% intervals. Count all
missing-feature reasons by split and publish aggregate results only. Do not
promote the challenger from this unpriced retrospective, change current
qualification, or claim a wagering edge; matching historical executable
prices and later prospective results remain required.
