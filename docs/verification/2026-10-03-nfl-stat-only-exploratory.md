ï»¿# NFL stat-only receiving challenger: exploratory temporal replay

A separate stat-only receiving correction was tested because the transferred workload
candidate requires complete target counts for every prior played game, which are
present for only 137 of the 233 source-backed receiving player/prop forecasts
in the retained October 3 cohort. This study uses already retained files and
no provider, database, or betting calls. It changes no consumer probabilities
or qualification gates.

The script verifies the SHA-256 of the four retained free nflverse Parquet files,
joins regular-season player rows to the exact game schedule, rejects duplicate
player/game rows, and uses the existing fixed NFL temporal partitions: 2024 fit,
September-October 2025 selection, and November 2025-February 2026 evaluation.
Each research line is determined from the player's preceding ten recorded games;
no target-game outcome enters its own features. The model removes the target
workload feature and fits or selects the existing candidate families on the
stat-only examples. Evaluation weights games equally, then player/games and
lines. The role-relevant line checks require at least 19.5 receiving yards or
2.5 receptions. Those cutoffs were added **after** inspecting the broad
aggregate result, so the narrow comparisons are exploratory, not untouched
holdouts. A further sensitivity filters to 2026 player/prop identities with
source-backed forecasts in the independently retained October 3 quote pair;
that is a survivorship-selected universe, not a historical market cohort.

| 2025 evaluation slice | Prop | Examples | Games | Selected challenger | Baseline Brier | Challenger Brier | Difference |
|---|---|---:|---:|---|---:|---:|---:|
| All synthetic lines | Receiving yards | 10,226 | 150 | L2 0.01 | .06891 | .06649 | -.00242 |
| All synthetic lines | Receptions | 9,120 | 150 | L2 0.1 | .06755 | .06426 | -.00329 |
| Higher synthetic lines | Receiving yards | 2,861 | 150 | L2 0.01 | .21287 | .20521 | -.00766 |
| Higher synthetic lines | Receptions | 2,817 | 150 | L2 0.01 | .21065 | .19599 | -.01466 |
| Higher lines, 2026 quoted players | Receiving yards | 1,663 | 146 | half-life 16 | .22482 | .22031 | -.00452 |
| Higher lines, 2026 quoted players | Receptions | 1,555 | 149 | L2 0.1 | .22235 | .21202 | -.01033 |

All differences favor the challenger within these retrospective, **unpriced**
examples. The last two game-cluster 95% descriptive intervals are
[-.00703, -.00200] for receiving yards and [-.01629, -.00436] for
receptions. They are not adjusted for inspecting multiple variants, and
the 2025 outcomes have been examined by earlier research. The low all-line
Brier scores mostly reflect near-zero synthetic lines; the higher-line rows
give a more relevant, still unpriced check.

The fitted data have participant stat rows, while the source-backed live
baseline requires all positive-snap played games and may recover missing
stat rows separately. The coefficients have **not** been validated across that
distribution shift. Original pregame source versions, injury status, actual
sportsbook lines/prices, transaction costs, and prospective settled outcomes
are absent here. No promotion, win-rate claim, ROI, or market edge follows.
The next model experiment must use a separately frozen stat-only transfer,
preserve the complete-history source gate, and collect forward matched
quotes and independently settled outcomes before any consumer use.

The ignored aggregate report is
.local/nfl-stat-only-exploratory-20261003.json with SHA-256
c44edb356c163113140863d22d0a1b62440be8bff11df6edae0e39ca7eb69557.
Reproduce from the retained private .local/team-share-sources and
.local/verified-timely-pair-20261003 files:

    $env:PYTHONPATH='src'
    .\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-03-nfl-stat-only-exploratory.py

## Corrected played-game transfer sensitivity

A second offline script, [2026-10-03-nfl-stat-only-corrected-transfer.py](2026-10-03-nfl-stat-only-corrected-transfer.py),
takes the **already fitted and selected broad-cohort coefficients** from the
first report. It verifies the pinned 2024-25 player-stat and snap files, the
crosswalk, and the game schedule. It forms complete positive-offense-snap
histories for October 3 quoted player/prop identities. Each example uses a
synthetic higher receiving line from strictly prior played games and targets
only November 2025 or later, after the selection window. No transfer
coefficient is refitted or chosen on these corrected-history outcomes.
A missing weekly target row is handled as zero only in the snap-backed
sensitivity; the explicit-target-stat subset excludes it.

| November 2025 onward, corrected history | Examples | Games | Matched 20–40 history Brier | Transfer Brier | Transfer minus matched history | Game 95% |
|---|---:|---:|---:|---:|---:|---:|
| Receiving yards, all snap-backed target games | 503 | 145 | .24752 | .23898 | -.00854 | [-.01752, .00045] |
| Receiving yards, explicit target stat | 494 | 145 | .24864 | .23986 | -.00878 | [-.01805, .00049] |
| Receptions, all snap-backed target games | 575 | 148 | .22576 | .21598 | -.00978 | [-.01594, -.00362] |
| Receptions, explicit target stat | 566 | 148 | .22787 | .21786 | -.01002 | [-.01651, -.00352] |

Against a separately computed **strict last-20** estimate on the same examples,
the transfer differences are -.01146 for receiving yards (game 95%
[-.02089, -.00203]) and -.01077 for receptions (game 95%
[-.01753, -.00401]). On explicit-target-stat rows the corresponding
differences are -.01111 and -.01045, with both game intervals below zero.
The matched 20–40 history baseline in the table is the fitted correction's
own offset. The current role shadow's recorded historical baseline instead
uses all retained 20-40 played games; its name must not be read as strict
last-20. The retrospective script explicitly computes the last-20 estimate
from `rows[-20:]`, so these reported retrospective differences themselves
are unchanged.

These are **exploratory unpriced retrospective** results. The late-2025
outcomes and 2026 quoted-player universe have been inspected in earlier
experiments; confidence intervals do not account for that reuse or multiple
comparisons. The corrected source files were published or updated after the
target games, and snap-only missing rows are a sensitivity assumption, not
proof of zero receiving production in a historical sportsbook settlement.
The receiving-yards Brier interval crosses zero. Receptions has a stronger
lead for a forward-only untraded challenger, but this is not a priced edge
or a 75% individual-pick win rate. The source gate, live thresholds and
consumer recommendation path stay unchanged.

The ignored aggregate report is
.local/nfl-stat-only-corrected-transfer-20261003.json, SHA-256
a72ff20d2b86f65f35c12e91467c8057a37e5744b1e159c7394f2a6731a0f396.
Run the first replay, then:

    $env:PYTHONPATH='src'
    .\.local\team-share-venv\Scripts\python.exe docs\verification\2026-10-03-nfl-stat-only-corrected-transfer.py
