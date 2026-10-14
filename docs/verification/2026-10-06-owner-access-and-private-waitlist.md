# Owner access and private waitlist

## Immediate production containment

The user selected GitHub `rahulp7801`. GitHub's authenticated `/user` response
binds that account to immutable ID `76501505`.

Production previously returned HTTP 200 for `/terminal` and `/api/scans`.
The existing Vercel project is on the **Hobby** plan. One targeted free
`rules.insert` operation added an active deny rule, retaining the original
rate rule and all release protections. Active firewall version is **2**.
The generated rule ID is
`rule_close_live_dashboard_pending_owner_o_auth_release_bX0AvG`.
The reviewable rule is `.github/security/private-dashboard-containment.json`.
Local before/after snapshots are retained under ignored `.local/`.

External production probes now return:

- `/`: 200, with the historical demo section still present.
- `/terminal` and `/terminal/nfl`: 403.
- All thirteen live API families, including NFL/NBA/CFB examples: 403.
- `/signals_cache.json` and an encoded `/api%2Fscans`: 403.

The deny rule locks the dashboard for the owner too. It is temporary privacy
containment, **not a completed GitHub login rollout**. The deployed landing is
still the old release; its live preview calls now fail rather than disclose
private data. No schema migration, app deployment or production merge occurred.
No payment, upgrade, new provider collection or bet was initiated.

A full-config PUT was rejected because it attempted to revalidate the old
rate rule as a currently unavailable plan feature. The documented targeted
PATCH succeeded without changing that original rule or purchasing protection.

## Reviewed application behavior

Pinned stable `next-auth` 4.24.15 supports the pinned Next.js 16.3.6. GitHub
OAuth uses state and PKCE, with the library's CSRF-protected sign-in/sign-out
and encrypted HttpOnly session cookies. Only provider `github` and account ID
`76501505` may establish the owner session. Username text, a different provider,
legacy tokens, client session updates and bearer headers cannot authorize it.
An eight-hour absolute owner-session age is enforced independently of cookie
refresh. Redirects remain on fixed application destinations; the dashboard
includes explicit sign-out. Browser sessions contain no provider access token
or email address. Auth logs expose generic messages only.

The proxy restricts private pages/data paths, and **every live route handler**
verifies the encrypted owner session before database or provider reads.
The terminal server component checks identity too. Missing identity settings
fail closed. Authenticated responses use browser and CDN `no-store` headers;
the existing bounded server snapshot cache stays behind the authenticated
boundary. Query/chronology/source/qualification checks remain unchanged.

The public landing no longer fetches live markets, games or scans. Its product
frame is explicitly illustrative. Historical demo source receipts and misses
remain visible. Navigation points to the actual demo anchor and waitlist.
The headline retrospective accuracy panel is replaced by product context,
price and evidence explanations; no win-rate/alpha promise is introduced.

## Durable waitlist boundary

Migration `0046_private_waitlist` creates a private schema, RLS-enabled entry
and counter tables, and one SECURITY DEFINER function with a fixed pg_catalog
search path. PUBLIC, browser, dashboard and worker roles cannot access it.
A separately provisioned writer receives only schema USAGE and function
EXECUTE, never table SELECT/INSERT or dashboard credentials.

The endpoint requires same-origin JSON submission and explicit access-update
consent, validates and normalizes an ASCII email, caps actual streamed input
at 2 KiB, rejects unexpected fields and uses a honeypot. The database enforces
30 requests/minute and 500/day globally across processes and deployments.
Repeated signups keep one original entry and return the same generic receipt.
Storage failure/rate limiting never produces a saved-success message.
No email is sent by this change. No entries are readable through an API.
A populated waitlist prevents a destructive downgrade.

Private publication verification reads exact `markets:<sport>` and
`schedule:<sport>` snapshot receipts with the existing restricted worker
credential and verified TLS. It does not export an owner session to CI or
make public data APIs readable. No new quote collection is triggered.

## Dependency security

The current dependency audit surfaced two high-severity advisories. Compatible
patches update Sharp 0.35.4 to **0.35.5** and source-map-js 1.2.1 to **1.2.2**;
Next.js remains 16.3.6 and the frozen sports/evaluation dependencies are unchanged.
The patched installation reports **zero vulnerabilities** in the production audit.
Sources: [Sharp maintainer advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w)
and [source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

## Verification

- The complete frontend suite passed all 322 tests, including the final safe-redirect regression.
- The nine focused owner/redirect/cache/release checks passed on the final logic.
- Twenty release-script regression tests passed.
- Two real PostgreSQL waitlist/receipt tests passed after the schedule-key correction.
- The full migration chain passed all twelve migration tests against disposable PostgreSQL.
- TypeScript and lint passed. Python Bandit passed for the migration/receipt verifier.
- The final dependency-patched production Webpack build, TypeScript and changed-file lint passed.
  The HTTP smoke exposed a missing owner-sign-in footer link; that link and inherited
  landing text encoding were repaired before the accepted final build.
- All 32 real HTTP checks passed against that final local production build: public
  landing, private terminal redirects, every live API family, JSON-file admission,
  secure CSRF cookies and PKCE/state authorization URL, real encrypted synthetic
  owner session admission, nonowner/expired rejection, and waitlist 202/400/403/405.
  No GitHub redirect was followed. Local fixtures use Next's canonical localhost
  origin; the 127.0.0.1 alias fails the same-origin check rather than weakening it.
- Two identical valid HTTP signups persisted exactly one entry with access-update-v1
  consent in the disposable database. No production waitlist data was written.
- Final desktop (1440 px), phone (390 px) and phone waitlist screenshots were
  inspected in an isolated local browser with exact device emulation. No horizontal
  overflow was measured; the waitlist field fits the phone viewport and clears the
  fixed header. The dark-theme CTA/brand contrast defect was repaired; action text
  contrast is 5.06:1. The final build and all 32 HTTP checks passed after that CSS fix.
- Real GitHub owner/second-account OAuth round trips remain pending configuration
  and deployment; synthetic sessions do not establish that production result.

## Activation requirements

- `NEXTAUTH_URL` and a generated sensitive `NEXTAUTH_SECRET` are already saved
  in Vercel's production server environment; values were not logged/committed.
- The browser runtime fails to start. The user was asked to create a **free**
  GitHub OAuth application and save `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
  in Vercel production, without sending the secret in chat.
- Homepage: `https://agentic-ev-analytics-platform.vercel.app`.
- Callback: `https://agentic-ev-analytics-platform.vercel.app/api/auth/callback/github`.
- Apply the reviewed migration through the existing production schema gate.
  That gate now runs the dedicated [waitlist credential provisioner](2026-10-06-protected-waitlist-provisioning.md),
  verifies least privileges and actual generated-password login, and stores
  only a sensitive production `WAITLIST_DATABASE_URL`. It does not rotate
  existing credentials. Retain verified TLS/CA settings; the provisioner and
  production waitlist persistence still await the protected release.
- Required private CI/CodeQL and production environment protections remain.
  Private head 8bf09fbc63e6bfaaf59d0d49b217090377260714 has exact-head
  [CI run 37528996673](https://github.com/rahulp7801/agentic-sports-forecaster/actions/runs/37528996673):
  all five failed jobs have zero runner steps; schema/release/deploy jobs were skipped.
  The frontend annotation explicitly cites failed account payments or the spending limit.
  This is not evidence that the local test suite failed.
  The account gate currently prevents runner steps. Do not increase spending,
  override branch protection or merge the unapproved reserve bypass PR #194.
- Do not remove the containment rule until the reviewed owner-auth deployment
  and all necessary secrets are ready. The old release has no app login guard.
  The existing live API preflight returns 403 under containment and the final
  private verifier requires app-generated 401 after containment removal.
  The missing contained-release flow is now implemented in the protected job;
  see [contained owner release transition](2026-10-06-contained-owner-release-transition.md).
  A temporary diagnostic deny tests the actual app guard while ordinary public
  traffic remains blocked, then scoped recovery protects incomplete transitions.
  It remains private/reviewable code, not a completed production deployment.
- Production acceptance: public landing/demo, durable idempotent waitlist;
  anonymous APIs 401, anonymous terminal redirect; real owner GitHub login
  succeeds, a second GitHub account is denied; owner live responses no-store.

## Prospective evidence checkpoint

The original research goal remains active. No frozen model, rule, prospective
membership or evaluation version changed. Next checkpoint remains
**October 8 17:25 UTC / 10:25 AM Pacific**: verify the scheduled pregame capture,
receiving-integrity and recent-gap receipts, original source/schedule timing,
and private server-dated anchor before kickoff. Missing pregame evidence cannot
be manufactured afterward. The single October 4 slate cannot prove 75% wins
or a sizeable repeatable edge.
