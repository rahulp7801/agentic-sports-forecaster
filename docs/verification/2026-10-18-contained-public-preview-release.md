# Public preview release with live routes contained

## Problem and scope

Current platform code and the deployed landing page have diverged. Recent default-branch CI has passed its code, schema, restricted database-read and dedicated waitlist-credential checks, but the authenticated release preflight has stopped because owner GitHub OAuth configuration is incomplete. The existing external containment rule still denies live API, terminal and JSON routes.

This release adds an explicit manual `public_landing_only` option, defaulting to false. It deploys the reviewed public landing page, illustrative demo and waitlist while requiring that exact containment rule to remain active throughout. It does not certify owner sign-in. The existing authenticated release path retains its own checks and transition controller.

## Release gates

- Only an original-repository owner dispatch against current `master` can select this mode. It cannot be combined with the existing force-authenticated-release input. A job without secrets rejects conflicting inputs before production jobs.
- All normal backend, frontend, PostgreSQL, secret-scanning and worker-image jobs, production schema readiness, restricted transaction-pool reads and dedicated waitlist provisioning must pass. Standard free public-repository runners remain in use.
- The controller makes GET-only control-plane requests. It pins repository, owner, current branch head, Vercel project, frontend build root and free Hobby team identity. Environment metadata is read with decryption disabled. The production waitlist credential must be unique and unbranched; origin/session settings remain required.
- The current default-branch Actions checks must pass. The reviewed squash must map uniquely to a merged pull request in the original repository, and immutable Git commit trees for its reviewed head and deployed squash must match exactly. All eight required Actions checks and the real final GitHub Advanced Security `CodeQL` aggregate must have succeeded for that reviewed head. A PR-only aggregate is never invented for the default branch or replaced with an analysis job. GitHub documents the aggregate as a [pull request check](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-code-scanning-alerts/triage-alerts-in-pull-requests).
- Preparation records the exact guard ID/version and a digest of unrelated firewall configuration. Finish requires them to match, requires no diagnostic exception, rechecks current head and gates, and binds the canonical production alias to the deployed commit metadata.
- No firewall rule is inserted, removed, restored or patched by this controller. A missing guard or configuration drift fails closed. An interrupted or uncertain deployment receives no automatic mutation retry.

## Public HTTP verification

The separate contained verifier only contacts the canonical production origin, omits credentials, refuses redirects, bounds requests and response bodies, and permits only bounded local Next.js CSS assets. It verifies current landing/demo/waitlist markers, styles, exact media types and security headers.

Every live API, terminal and JSON probe must return exactly HTTP 403 with `no-store`, including the existing perimeter's `private, no-store, max-age=0` header. HTTP 200, application-authentication HTTP 401, redirects, positive cache ages and shared-cache headers all fail this contained mode. The normal authenticated verifier still requires its original HTTP 401/307 behavior.

The login page must show pending owner configuration and a genuinely disabled GitHub owner button. Waitlist probes are GET, cross-origin POST and a same-origin invalid `{}` body. None supplies an email or reaches the insertion branch. Schema and credential readiness are checked separately by the production schema job; these HTTP probes do not claim a successful signup.

A successful HTTP verifier result explicitly reports `public_surface_verified: true`, `live_routes_contained: true` and `owner_authentication_verified: false`. The controller's completion receipt reports status `public_surface_verified`, `containment_active: true` and `owner_authentication_verified: false`. Owner access stays pending until the separate authenticated release succeeds.

## Verification and limits

Focused verifier tests cover every protected route returning exposed, app-authenticated or redirected responses; cache controls; stale landing/CSS; disabled-button lookalikes; invalid media types; external stylesheet injection; body/asset limits; and sanitized errors. Controller tests use injected metadata and HTTP clients. No test deploys, changes firewall rules, accesses provider quotas or submits waitlist addresses.

The focused public verifier passed 12 tests, the final controller passed 61 tests, and workflow configuration passed 14 tests locally. The combined frontend/release Node test run found one sandbox permission failure in the existing synthetic Git fixture; its complete 15-test file then passed on the ordinary Windows host. The new verifier also passed ESLint. Real required GitHub checks must pass for the final reviewed revision. This note does not substitute for those checks.

Preparing and merging this code does not activate the manual release. Production verification requires a real successful protected workflow and canonical-origin readback. A release does not establish qualified picks, prospective admission, profitability or an edge. Frozen model/evaluation versions, qualification thresholds, collection budgets and original evidence receipts are unchanged.

## API compatibility correction

The first contained public dispatch, run `39124755186`, passed its code and schema gates but stopped at `reviewed_pull_request_missing_or_ambiguous` before the Vercel deployment step. Actual API readback showed that GitHub version `2026-03-10` omits `merge_commit_sha` from both the associated-PR list and individual PR response. GitHub documents this [breaking response change](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes?apiVersion=2026-03-10).

The controller now explicitly pins the supported `2022-11-28` API contract. Actual reads with that version returned the exact merged commit for both endpoints. That contract remains supported until March 10, 2028, according to GitHub's [API version policy](https://docs.github.com/en/rest/about-the-rest-api/api-versions?apiVersion=2026-03-10). The literal request header is tested, and missing merge-SHA fields still fail closed. A closed PR, merge timestamp, matching tree or successful check alone never replaces the exact merge identity. No deployment or firewall mutation occurred during the failed prerequisite check; it is not an ambiguous deployment to retry.

The compatibility revision passed all 64 focused controller tests and independent review. It changes the fixed API header, adds explicit missing-field regressions and preserves all merge, tree, CI and containment gates.
