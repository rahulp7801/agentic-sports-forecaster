# Complete pregame evidence and durable fixed-cohort handoff

**October 6:** first result collection and both frozen scores are now complete.
See [actual results and independent follow-up](2026-10-06-fixed-results-and-recent-gap-validation.md)
for the scheduled launch refusal, one-time recovery, result denominators,
research findings and the next pregame checkpoint. Earlier pending-task notes
below describe the handoff before results.

## New prospective evidence, October 5 23:05 UTC

The final scheduled unsigned fee observation (22:58 UTC), exact-ticker quote
observation (23:00 UTC), and private anchor (23:05 UTC) all finished with
Task Scheduler exit 0. GitHub's private PR #345 timeline independently records
commit `44b41c576c5df46f9a674bf17cfa3171cf2f5f98` at **23:05:19 UTC**, before
the last group's **October 6 00:15 UTC** kickoff. The private
`research/fixed-prelock-20261006T0015-anchor` ref preserves that exact object.
All four original fee/quote/report file hashes match its tracked
`20261006T0015-fixed-prelock-anchor.json` marker. Later release amendments must
leave the preservation ref at this object. Local commit dates alone are not
pregame proof.

An offline replay of all six retained kickoff groups now matches **70/70
fixed decisions over 15 games**. Selected-side displayed asks rose for 23,
fell for 24, and stayed unchanged for 23. Mean ask movement is
`0.0007142857142857142857142857143` per contract (about **+0.0714 percentage
points**), or `0.0008555555555555555555555555553` with equal game weighting.
These later pregame asks are not closing prices, fills or an outcome.

The corresponding six-group one-contract fee scenario covers **70/70**.
Modeled total cost is **36.4972** direct and **36.69** nondirect. Both scenarios
require **37 binary wins out of 70** to break even, conditional on every
contract settling binary and one fill at each recorded displayed ask with
the modeled fee. Void/missing results and executable fills are unverified.
These modeled costs are not charges, returns or evidence of an edge. The
original selected sides, probabilities, candidate set and evaluation versions
remain frozen. No outcome was opened or fetched for these replays.

Ignored aggregate reports and exact byte SHA-256:

| Report | SHA-256 |
| --- | --- |
| `.local/stat-only-prelock-series-20261005-final.json` | `6ab545e3ddff20636add8fdcb0f5cd96699439316e6196f3bc6c6427d887688f` |
| `.local/stat-only-prelock-costs-20261005-final.json` | `6e1c511e2abbdda8e7fe9e9f1ae5704462aaca87fc75fb5c5df5a1e7ac29bc7a` |

Earlier 66/70 reports remain retained as earlier checkpoints; their four
missing observations have now arrived through the original scheduled tasks.
No redundant quote collection was triggered.

## Remove the fixed-cohort dependency on temporary storage

The existing postgame collector still depended on a Temp checkout and input
directory. Its two offline scorer actions used the durable source launcher
but also depended on Temp inputs. That created an avoidable cleanup/restart
risk before the pending result gate.

Copied **38 explicit evidence/source files, 23,065,576 bytes**, to ignored
`.local/fixed-cohort-20261004` in the durable private checkout. Every destination
was checked against the original raw SHA-256 and size. This includes the
original pair/market archive, source manifest and eight source files, schedule,
forecast/quote/decision inputs and six fee/quote receipt/report groups. No
credential, model alteration or settlement was added. The ignored copy manifest
has SHA-256 `007260f612ee8bad20711d8935c6cda45c8ee0edd1b68a5e62bb3ca88849fdc6`.
All 38 copies were checked again during the scorer-action rehearsal.

The collector, shared clock observer and venue reader in the durable checkout
match the retained Temp source after normalizing Windows line endings. The
frozen forward evaluator matches byte for byte. The tracked launcher now
allows the existing settlement-capture module and verifies its origin inside
this checkout, overriding the copied virtualenv's old editable-install path.

Only the actions of these three existing one-shot tasks changed. They now use
the durable Python executable, tracked launcher, working directory and copied
inputs; no action contains `AppData\Local\Temp`. Triggers, principals and
settings were compared before/after and preserved. A partial first configuration
command failed to persist backups and update the collector; actual task actions
were inspected and the collector was repaired with a fail-fast update. The
collector's original/final XML and all three verified current definitions are
retained locally; original XML backups are not claimed for both scorer actions.

| Task | October 6 UTC / Pacific | Result path relative to private checkout |
| --- | --- | --- |
| `SportsbetStatOnlySettlement20261006T1400` | 14:00 / 07:00 | `.local/fixed-cohort-20261004/stat-only-settlement-20261006.json` and its report |
| `SportsbetStatOnlyScore20261006T1415` | 14:15 / 07:15 | `.local/stat-only-forward-after-result-20261006.json` |
| `SportsbetStatOnlyNetScore20261006T1420` | 14:20 / 07:20 | `.local/stat-only-prelock-paper-result-20261006.json` |

The collector retains its full-cohort **October 6 06:15 UTC** gate and maximum
**23 unsigned public GET batches for the original 452 exact contracts**.
The scorers are offline. The API daily/rolling limits, staged reserve,
qualification thresholds and frozen evaluator are unchanged. No task was
started manually. All three are Ready for their original trigger times and
still require this workstation to be on and the user logged in.

## Verification and exact next checkpoint

- **21 focused tests passed** across launcher, settlement capture, fixed-score
  and fee-inclusive result suites. A foreign PYTHONPATH cannot redirect the
  newly allowed collector module.
- Pinned Bandit passed for the launcher. No dependency or frontend change is
  included in this increment.
- The real durable-bundle preflight reproduced **452 original contracts, 233
  source-eligible contracts, 144 forecasts, 70 decisions and 15 games**. Forecast
  commitment is `ad74381b6d7b1707c0c6f2b5d0ab9e22e3e14d4e6eafc7145902656785837f13`;
  candidate commitment is `b8750ea51d18703c9f23b67dada8d7f3939df2cf20238dd1615b598b418d4d06`.
- Rehearsing the actual updated collector argv before the gate replayed inputs,
  then exited 2 with **no venue read** and no result/report file created.
- Rehearsing both actual updated scorer argv before the gate exited 1/2 with
  explicit **no settlement file opened / no settlement input read** errors.
  Neither output was created. Local logs and action proof are retained.

After **October 6 14:20 UTC (7:20 AM Pacific)**, inspect each task's actual exit
code and raw receipt, authenticate clock/hash/scope/chronology, and verify the
two score reports retain every missing or nonbinary state. Compare selected
results against the same recorded asks and fees. Do not select a new subgroup
after results arrive. An incomplete result stays unavailable; it cannot
publish a consumer pick or promote a model automatically.

The single correlated 15-game slate cannot establish repeatable alpha or the
advertised 75% win rate. Current qualified picks remain zero. Hosted private
CI and production remain blocked before runner steps by the previously
verified account payment/spending gate; the $0 stop budget and required
private CodeQL protection remain intact. No production merge or deployment
occurred during this handoff.
