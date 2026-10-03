# Private pregame anchor for the last fixed NFL paper observations

The original October 4 stat-only cohort remains 70 paper decisions in 15
games. Its first asks, selected sides, model probabilities, and evaluation
versions remain frozen. The last two free unsigned fee and exact-ticker price
observations are scheduled for October 5 00:03/00:05 UTC and October 5
23:58/October 6 00:00 UTC. Their corresponding kickoffs are 00:20 and 00:15
UTC. No order, bet, purchase, paid Odds API credit, or result request is made.

`kalshi_stat_only_fixed_anchor` reads the four bounded local JSON outputs for
one scheduled group (fee receipt/report and exact-ticker receipt/report). It
requires all four, computes their exact byte SHA-256 values, and writes only
those hashes to a tracked private marker. It requires a clean checkout on the
expected release branch and an exact match between local and remote HEAD,
then amends the single PR commit with a force-with-lease push. A separate
private research ref preserves that exact commit after later amendments. The
helper refuses to start within two minutes of kickoff or push within one
minute of kickoff. It makes **no venue or model request**. The later scorer
still checks every raw receipt; a hash alone does not make a quote valid.

The two limited-user one-shot Windows anchor tasks run after their already
scheduled collectors, at October 5 **00:10 UTC** and October 6 **00:05 UTC**.
They require the workstation to be on and the user logged in. If a collector
misses its window, a receipt is invalid, the branch moves, GitHub is
unavailable, or the push arrives after kickoff, the evidence remains missing;
the task must not create or backfill a price. Inspect the task exit code, the
tracked marker, the private preservation ref, and GitHub's server-dated PR
force-push event before calling either marker a pregame remote proof. The
local `local_hashed_at` and Git commit dates are not the chronology authority.

Focused tests exercise incomplete/malformed/late receipts, changed remote
HEAD, exact tracked hashes and push/ref commands without a network call. The
fixed cohort, consumer threshold, qualification, and outcome gate are
unchanged. This improves the future paper evaluation's chronology evidence;
it establishes neither price persistence nor a profitable edge.
