# October 4 production availability checkpoint

Read-only observation at approximately 2026-10-04 10:30 UTC. These are
deployed API responses, not a replay of the private release branch. No quote
provider, paid credit, order, or wager was used for this check.

| Sport | Last scan (UTC) | Eligible | Completed | Budget deferred | Quotes | Model estimates | Current picks | Authenticated historical picks |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| NFL | Oct 3 12:39:37 | 14 | 0 | 14 | 0 | 0 | 0 | 4 wins / 8 settled across versions |
| CFB | Oct 3 12:39:43 | 54 | 0 | 54 | 0 | 0 | 0 | 1 win / 2 settled across versions |
| NBA | Oct 3 12:39:40 | 0 | 0 | 0 | 0 | 0 | 0 | 0 settled |

Source: deployed [`/api/scans`](https://agentic-ev-analytics-platform.vercel.app/api/scans),
[`/api/picks?sport=nfl`](https://agentic-ev-analytics-platform.vercel.app/api/picks?sport=nfl),
and corresponding CFB/NBA pick endpoints. The NFL and CFB scan records say
`rolling_credit_limit`, and the API marks all three scans `stale`. A zero-pick
board here does not show that the model evaluated current market prices and
rejected every candidate: the scan reports **zero quotes and zero model
requests**. The Oct 3 recorded allowance reason explains that scan, but is not
proof that the rolling allowance still blocks a future scan.

The deployed [`recommendations` metrics](https://agentic-ev-analytics-platform.vercel.app/api/metrics?cohort=recommendations&sport=nfl)
default to the current NFL model version `empirical-jeffreys-v4-nfl-history-v1`:
one settled pick in one game, one win, no CLV observations, and no game-cluster
interval. Current CFB and NBA model versions have zero settled picks. The
all-version 4/8 NFL and 1/2 CFB board histories must not be presented as
current-version performance. Neither view establishes a priced edge or a 75%
individual win rate.

The private repository's scheduled [`Public market data` run 37189906165](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37189906165)
(Oct 4 08:44 UTC) and [`Live paid market data` run 37189167505](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37189167505) (08:30 UTC)
both failed before any step ran; their runner names were empty. The private
release [PR #345](https://github.com/rahulp7801/agentic-sports-forecaster/pull/345)
exact-head [CI run 37196524684](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37196524684) likewise failed its five code
jobs with zero steps, while release/deploy jobs were skipped. This is an
independent operational cause of the missing fresh scan, not evidence of model
quality or a failed quote-provider response. A zero-step failure also means
these runs made no paid provider calls.

The exact-head backend [check annotation](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37196524684/job/111419467534)
and the scheduled public-market check both state: "The job was not started
because recent account payments have failed or your spending limit needs to
be increased." GitHub gives those as alternatives; the annotation does not
establish which applies. The jobs completed in about three seconds with no
runner and no steps. A read-only personal billing-usage API request returned
404 and said this token needs the `user` scope, so account usage was not
independently verified. No payment method or budget was changed.

## Recovery and evidence gates

1. Preserve the existing 20-credit daily, 450-credit rolling and staged
   pregame-reserve limits. Never fill the board from unsupported estimates.
2. Restore a genuinely executing, protected private CI/scheduled scan path
   without charges. The owner reports a GitHub Actions budget of $0 with
   stop-usage; GitHub's own job annotation confirms an account billing or
   spending-limit gate, without identifying which condition. Removing or
   bypassing branch checks has previously failed automatic
   approval review. The private repository's three required CodeQL checks are
   unavailable without a GitHub Code Security license; retain protection
   until the owner approves a reviewable adjustment. The remaining five CI
   jobs and production release are also currently zero-step/skipped.
3. Once jobs actually run, inspect the next scan's eligible/completed/deferred,
   quote and model-estimate counts. Diagnose the allowance at that **new**
   capture time before changing ingestion or qualification logic.
4. Score the already frozen Oct 4/5 free public Kalshi paper cohort after
   authenticated venue outcomes, retaining the fixed 70-candidate denominator,
   matching ask prices, pregame chronology and game-cluster uncertainty. The
   first fixed fee/quote tasks are due Oct 4 12:13/12:15 UTC; the full venue
   outcome gate is Oct 6 06:15 UTC. This separate prospective test cannot by
   itself validate an NBA/CFB recommendation edge.

The [GitHub CodeQL private-repository requirement](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/private-repository-enablement)
and [private GitHub-hosted runner billing](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
are documented by GitHub. No plan upgrade, paid product, runner registration,
budget increase, branch-protection change or production deploy was made here.

GitHub says ordinary [self-hosted runner usage is free](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
but this repository currently has **zero** registered self-hosted runners and
its CI and production workflows target `ubuntu-latest`. Registering a runner
on the owner's laptop would give repository workflow code access to that
machine; GitHub [warns that even private-repository runners can retain a
compromise and expose secrets](https://docs.github.com/en/actions/reference/security/secure-use).
A disposable isolated runner would require a separate reviewed workflow,
credential boundary and host setup. It would not supply the three unavailable
CodeQL results or authorize a protected merge. Therefore a runner was not
registered as an improvised workaround for this release gate.
