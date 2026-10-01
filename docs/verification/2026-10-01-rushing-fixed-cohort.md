# Fixed prospective NFL rushing audit

The first rushing-role accuracy audit (v1) verified the candidate, original paper
receipt, matched market price and settlement, but its review window did not
close after the minimum count. A later favorable subset could therefore have
turned its status to review required. Its code and results remain reproducible;
v1 must not support a 75% claim or production promotion.

Evaluation v2 starts at 2026-10-01 06:30 UTC. It retains candidate model
nfl-rushing-role-shadow-v1, its source and quote checks, and the original
raw-model paper selector. It locks the first 50 verified original rushing
selections after that time on which both the original model and recorded
rushing-role candidate give the selected side at least 75%. Receipt timestamp
and prediction ID break ties. Later eligible selections are reported as
excluded and cannot enter the closed cohort. The first 50 must all have
authenticated settlements across at least 25 distinct games.

Review requires the same predeclared evidence thresholds: observed win rate
at least 75%, a game-cluster 95% win-rate lower bound at least 75%, positive
flat-stake ROI lower bound at the original price, and candidate-minus-matching
market Brier 95% upper bound below zero. No automatic promotion or dashboard
pick change follows. An incomplete or underpowered fixed cohort cannot be
extended or re-selected after outcomes are seen. Reports and underlying paper
picks remain private.

The v2 implementation pins the v1 helper source hash, while the v1 source
audit rechecks the immutable receipt and source commitments. The v1 candidate
model is unchanged. The evaluation runs offline on Linux CPython 3.12 because
the committed gzip source bytes use that runtime.
