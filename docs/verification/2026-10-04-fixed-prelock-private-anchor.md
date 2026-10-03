# Private pregame anchor for the last fixed NFL paper observations

**Latest checkpoint:** both private pregame anchors are now verified. The
final six-group replay covers all 70 decisions and fee scenarios. See the
[October 5 complete evidence and durable handoff](2026-10-05-fixed-cohort-complete-handoff.md)
for the final server-dated anchor, hashes, counts and exact result checkpoint.
The earlier 66/70 checkpoints below describe their original observation times.

The original October 4 stat-only cohort remains 70 paper decisions in 15
games. Its first asks, selected sides, model probabilities, and evaluation
versions remain frozen. The last two free unsigned fee and exact-ticker price
observations are scheduled for October 4 23:03/23:05 UTC and October 5
22:58/23:00 UTC. Their corresponding kickoffs are October 5 00:20 and October 6 00:15
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
scheduled collectors, at October 4 **23:10 UTC** and October 5 **23:05 UTC**.
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

On October 5, the first anchor task reported exit 0. GitHub's private PR
timeline independently recorded commit
`2f3215a2c71413bf0bea8965b7b382bb4eb25ad3` at **October 4 23:10:23 UTC**,
before the October 5 00:20 UTC kickoff; the private
`research/fixed-prelock-20261005T0020-anchor` ref points to that exact commit.
The recorded marker contains all four receipt/report hashes. The second
anchor remains future. Earlier prose used an incorrect UTC conversion for
the collector times; the task triggers and receipt bytes were not changed.

All four anchored files were checked on October 5 and retain their committed
hashes. The existing offline prelock-series scorer replayed all original
source/model/quote/decision inputs plus the five observed kickoff groups. It
matched **66 of 70** fixed decisions over **14 games**; the remaining four in
the October 6 00:15 UTC group were not yet due. Selected-side displayed asks
rose for 21, fell for 22 and stayed unchanged for 23. Mean ask change was
**-0.00030303** per contract (about -0.03 percentage points), and -0.00033333
with equal game weighting. This nearly flat price movement is not an outcome,
fill, closing price or profitable edge. No new venue call was made for this
replay. The ignored aggregate report is
`.local/stat-only-prelock-series-20261005-new.json`, SHA-256
`4c336adf920c50583577f57e41bdd2ce99e9a803eea0fa4fa8237e0ef8ed3fde`.

On October 5, the final anchor's still-future trigger was moved from October
6 00:05 UTC to October 5 **23:05 UTC (4:05 PM Pacific)**, five minutes after
the original 23:00 quote task. This reduces the need for the laptop to stay
available for an extra hour and gives the private push more time before the
00:15 kickoff. Before/after XML proves the action, principal and settings
unchanged; the definitions are backed up locally. No capture was started or
rescheduled, and no extra provider request is introduced.

An offline fee/price replay on the five retained groups modeled one contract
for **66 of 70** original decisions. Hypothetical subset costs total
**34.3480** in the recorded direct-fee scenario and **34.53** in the nondirect
scenario. Four missing fee/quote pairs remain explicit, so full-cohort costs
and break-even win counts are null. These are modeled costs, not charges,
fills or a return. The ignored aggregate report is
`.local/stat-only-prelock-costs-20261005-verified.json`, SHA-256
`22b681eb3b0027cd5b8924f9b22a7520c311a3fa604bfb4b58ca3a564833e04c`.
