# Market-information diagnostic and deployment access audit

## Original-slate diagnostic

The completed local diagnostic asks whether the capped-prior role probability
adds information when the matching market midpoint is already present. It uses
the unchanged original role receipt, all 308 original forecasts, the same
303 authenticated binary results, 15 games and 145 players. Five nonbinary
outcomes and 144 unavailable role forecasts remain recorded in the scope.
Original source/score hashes and the full-cohort settlement gate were checked.
No source, quote or settlement request was made.

There is one coefficient, restricted to [0, 1]:
`p = market + weight * (capped8 - market)`. It minimizes Brier error with equal
game weights. For each held-out game, its coefficient is fit using only the
other 14 games. There is no prop-bin search or result-based contract filtering.
An all-games fit is separately labeled in-sample.

On the same 303 pairs, lower scores are better:

| Forecast | Pooled Brier | Pooled log loss |
| --- | ---: | ---: |
| Original matching market midpoint | 0.243873 | 0.680379 |
| Capped8 role probability | 0.264754 | 0.728818 |
| Whole-game-held-out market blend | 0.247871 | 0.688651 |
| In-sample market blend | 0.243922 | 0.680514 |

The all-games capped8 coefficient is 0.088063. Its equal-game Brier difference
versus market is -0.000438; game and player cluster intervals both cross zero.
This equal-game fitting objective differs from the pooled table. The held-out
blend has an equal-game Brier difference of +0.003781 and log-loss difference
of +0.007825. It does not improve the market on this slate.

Both this analysis and the capped8 hypothesis were defined after seeing the
original results. Leaving out a game during coefficient fitting does not
establish pregame chronology or independent replication. The existing cluster
intervals resample the scored predictions with their coefficients held fixed;
they do not include refitting uncertainty or erase the overlapping training
sets. These observations support rejecting promotion of this fitted blend.
They cannot establish that every possible context model lacks an edge.

The script, full report, fold coefficients and original evidence remain under
ignored local storage. Future raw evidence stays local, as the owner instructed.
No new remote raw-evidence upload or draft was created. The previously authorized
original-cohort recovery draft is unchanged. There is no change to the frozen
prospective capped-prior protocol, teammate protocol, qualification thresholds,
market execution claims, reserve or API-credit limits. Qualified picks remain
unproven by this diagnostic; ROI and CLV remain null.

## Anonymous deployment probes

At 2026-10-08 06:43:52 UTC, a read-only audit inspected the current production
deployment and six recent READY deployments in the existing project. Three
authenticated metadata GETs established their actual generated hostnames.
Anonymous requests used no provider credential, session or protection-bypass
header and did not follow redirects or retain private response bodies.

- The canonical public landing returned 200.
- Canonical `/terminal` and `/api/picks?sport=nfl` returned 403 with the
  provider's `deny` mitigation header.
- All six distinct generated deployment hosts returned 302 to `vercel.com`
  for the landing, terminal and picks routes.
- The project reported `ssoProtection.deploymentType: all_except_custom_domains`
  and no configured project protection-bypass entries.
- A separate documented team-members GET returned one confirmed member:
  `rahulp7801`, GitHub `rahulp7801`, role OWNER. It does not inventory separately
  granted branch access or deployment-specific sharing links.

The sampled generated URLs provide no observed anonymous private-data bypass.
This bounded audit does not cover every retained historical deployment, alias,
sharing grant or previously downloaded copy. It made zero setting, membership,
firewall, billing or deployment mutations. Local metadata/probe receipts are
retained; no live quote collection was triggered.

Vercel documents that authentication protects selected existing and future
deployments, with project/team access and separately granted sharing paths:
[Vercel Authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication).
The September 9 announcement also makes production protection free on all
plans: [production protection availability](https://vercel.com/changelog/protect-production-deployments-for-free-on-every-plan).
No plan change is needed for this audit, and no setting was changed.

## Next evidence and release checkpoint

At **October 8 17:25 UTC / 10:25 AM Pacific**, inspect the already scheduled
capture/publisher exits, original source/quote/schedule receipts, timely role
and teammate study receipts, all three hash-only markers in the same preserved
private commit, server push before kickoff, and the local verified recovery
package or explicit failure status. At **October 10 17:25 UTC**, check the fresh
Saturday capture and Sunday context coverage. The new commitment supplies its
exact original full-cohort first eligible settlement time. Missing pregame
evidence cannot be recreated afterward.

The account CI gate, required private CodeQL, owner OAuth credentials and
protected waitlist configuration remain release blockers. This audit does not
remove the containment rule, bypass required checks, merge PR #194 or claim a
deployed GitHub owner-login release. Public landing/demo access and private
dashboard containment remain verified in the current production release.

## Complete retained deployment and alias inventory

The follow-up at **2026-10-08 14:20:16 UTC** replaces the six-deployment sample
with a paginated inventory of this exact existing project and owner team. Five
GET-only metadata requests exhausted the documented deployment and alias cursors:
**270 deployments (268 READY, two CANCELED)** and **two assigned aliases**.
The READY creation dates span September 10 22:45:52 UTC through October 1
02:20:57 UTC. No inventory record crossed the project scope, and every retained
READY URL and alias was a validated `vercel.app` hostname.

All **270 distinct READY/alias hosts** were tested anonymously at `/terminal`
and `/api/picks?sport=nfl`: **540 of 540 probes completed** by
**2026-10-08 14:21:54 UTC**. The 268 generated deployment hosts and the alternate
project alias returned 302 to `vercel.com` for both routes (**538 redirects**).
The canonical alias returned the existing provider's 403 deny for both routes.
There were **zero successful anonymous responses, zero unresolved probes and
zero missing hosts**. No redirect was followed; no provider credential, session
or bypass header was sent to a deployment; no private response body was saved.
Six concurrent read workers bounded the audit. No collection or new deployment
was triggered.

The metadata also reported zero project-level protection-bypass entries and
zero protection-bypass entries on either assigned alias. This inventory closes
the earlier gap for retained READY generated hosts and assigned aliases. It is
not a test using a separately granted user's session or a share-link secret,
and it does not establish that all deployment-specific grants, custom-domain
configurations, deleted deployments or previously downloaded copies are absent.
Such sharing can be distinct from team membership; no grant was silently
created, revoked or rotated during this read-only audit.

Both sanitized inventory/probe receipts remain ignored and local. Their SHA-256
commitments are `9b08958a2ecca4ecb075c1b65dffd76a7fd16c377404dfcea921e46e52f472a5`
(inventory) and `0971cac9a2e751b780759689913e9ed785017127a0066c71f03198cbd00310da`
(probes). Only this aggregate/hash account is retained in private review. Future
raw research evidence still stays local, and the original prospective research
refs and frozen source bytes are unchanged. Owner OAuth, protected waitlist
configuration, hosted CI and private CodeQL remain production activation gates;
no new edge evidence or usable owner-login deployment follows from this audit.

Endpoint and access semantics were checked against primary documentation:
[Vercel deployment inventory](https://vercel.com/docs/rest-api/deployments/list-deployments),
[alias inventory](https://vercel.com/docs/rest-api/aliases/list-aliases), and
[Vercel Authentication access paths](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication).
