# Security policy

Do not put credentials in issues, pull requests, screenshots, session notes, logs,
or sample configuration. Report vulnerabilities through GitHub's private
vulnerability reporting interface. If a credential is exposed, revoke it at its
provider first; deleting a file or rewriting Git history does not revoke access.

Keep local credentials in ignored `.env` or `.local/secrets/` files. Hosted
credentials belong in GitHub Actions secrets or server-only Vercel environment
variables. Never use `NEXT_PUBLIC_` for database passwords or provider keys.
Use the restricted worker and dashboard database roles, never the owner role.

CI scans the complete tracked source tree and every incoming commit using a
checksum-pinned Gitleaks release. Default rules are extended to catch provider
keys in prose. Findings are redacted; scanner reports and private diagnostics
must not be uploaded as public artifacts. GitHub secret scanning and push
protection provide additional checks, but no scanner detects every secret.

Before uploading public Actions evidence, the worker stages only the three
approved JSON archive directories. It checks raw and decoded JSON against its
configured credentials (including decoded database passwords and URL-encoded
forms), then runs the same redacted Gitleaks rules. Either failure blocks the
entire upload. Private directories and scanner reports are never staged. This
gate also applies when collection fails and partial evidence is retained.

## Public repository audit, 2026-09-11

The audit covered fetched branches and public pull-request heads (345 commits,
1,072 unique file objects), repository issue/PR comments, all 106 retained
workflow log archives, and the one available Actions artifact. Default Gitleaks
rules reported no findings. A private comparison against configured credential
values found the Odds API key in `SESSION_2026_03_27.md`, introduced in commit
`c3b823f`. The new provider-key rule independently detects that exposure.

The current file is redacted. **The historical credential remains exposed and
must be revoked.** The owner has been asked to replace the local and GitHub
secret values. Rotation is not yet verified. Incoming-commit checks prevent new
exposures; they do not claim the old history is clean. History removal requires a
coordinated rewrite and may also require GitHub Support to remove cached views
and pull-request references; forks and external copies cannot be recalled.

No other configured credential matched the audited material, and the default
scanner found no credentials in downloaded public logs/artifacts/comments.
This is evidence about the audited content, not proof that unknown or expired
credentials have never been exposed. Local paths, public CA certificates,
project identifiers and synthetic disposable-CI passwords are not secrets.

The platform is read-only with respect to betting and trading venues. Do not add
order execution or bypass provider access controls as part of a security fix.

## Public dashboard review, 2026-09-18

The expanded remote-history scan inspected 624 commits with the custom provider
rules. It still detects the historical Odds API credential described above;
an in-memory comparison confirmed it matches the currently configured local
key; the provider still accepted it at its free metadata endpoint. **Provider revocation and replacement remain required.** No credential
values or scanner reports are committed. GitHub reported no open secret or
CodeQL alerts; that did not detect this custom-provider exposure.

On 2026-10-04 at 16:42 UTC, a read-only GitHub Actions secret metadata check
showed `ODDS_API_KEY` was last updated on **2026-09-10 23:06:57 UTC**, before
this exposure was identified. The secret has therefore not been replaced in
the private workflow since the audit. Its value was not read; metadata alone
cannot prove whether the provider revoked the old key. Keep provider
revocation and secret replacement as a production release gate. Do not buy
credits, enter a card, raise limits, or trigger a quote read to test the key.
The private release now checks a one-way SHA-256 fingerprint of the exact
historically exposed key at every supported paid-source entrypoint, before
opening the shared credit ledger or making an HTTP request. It refuses that
credential without printing it. This prevents the application from continuing
to use the known exposed value; it cannot revoke the provider credential or
stop use by someone who already copied it. A newly issued free key can pass
the guard, subject to the existing 20-credit daily, 450-credit rolling, and
pregame reserve limits. Rotation and hosted-secret replacement are still
required before production collection resumes.
At 2026-10-04 17:54:33 UTC, the private repository variable
`DATA_PIPELINE_ENABLED` was set to `false` and read back from GitHub. This
disables the scheduled paid daily and pregame scan branches in `data.yml`
while the old hosted secret remains configured. The separate
`PUBLIC_DATA_PIPELINE_ENABLED` stayed `true`, and the 20-credit daily limit
stayed unchanged. The unconditionally scheduled NFL history refresh does not
inject `ODDS_API_KEY`. Manual workflow dispatch can still request a paid
operation, so this flag does not revoke the credential or replace provider
rotation. Keep automatic paid collection off until the exposed key is revoked,
the hosted secret is replaced with a new free key, and the protected release
with the exact-key guard has passed CI and deployment verification. Do not
purchase credits, add a card, or raise the established daily or rolling caps.

The live database review found Supabase's named `anon` and `authenticated`
default grants, including SELECT on the owner-executed game-log view. Table RLS
already restricted policies to the application roles, but the view's direct
grants could bypass the website's request limits. Migration
`0024_deny_browser_roles` revokes PUBLIC and named browser-role privileges on
the application's tables and view. Provisioning applies the same restriction.
Its downgrade deliberately retains this security restriction. Disposable
PostgreSQL regressions reproduce the provider grants, verify access denial and
preserved data, and verify the restricted reader/worker remain usable.

The default-ACL review also found browser grants automatically applied to new
objects. `0025_deny_browser_defaults` and provisioning revoke future table/view
and sequence defaults for the connected application creator in `public` and
`analytics`. Downgrade preserves the denial. Tests recreate provider defaults,
create new objects after migration/provisioning and verify denied grants/query
access without relying on table RLS. Provider-admin defaults are outside this
application creator's scope. New application functions require explicit PUBLIC
execution review; schema-level function revocation cannot override PostgreSQL's
implicit global PUBLIC execution default. Existing application RPCs remain
absent; the provider's event-trigger helper is not a callable application RPC.

The dashboard reader has no superuser, role/database creation, replication,
RLS bypass or schema creation privileges; its default transaction is read-only,
statement timeout is five seconds and connection limit is 12. Hosted frontend
connections must use `sslmode=verify-full`; custom CA connections also verify
the certificate and hostname. SQL inputs are validated and parameterized.

The intended edge policy is 240 dynamic requests per minute per source IP,
excluding static assets, retained in
[vercel-firewall.json](.github/security/vercel-firewall.json). **Enforcement is
not verified:** Vercel saved an initial rule but 260 bounded, lightweight,
read-only status requests within one window all returned 200. Subsequent
activation/correction attempts returned a plan-related 403. Account-side
activation is required before treating this as an effective protection.
Use the documented counting key `ip`, not the condition-field name
`ip_address`. Check the active configuration and preserve unrelated rules
before changing it; a full PUT replaces configuration. Vercel's documented
rate counters are regional, so per-IP allowances are not a global quota.
Validated public API responses share a ten-second edge cache while browser
responses remain uncached. The browser rechecks quote expiry; incomplete
qualified inspection exposes no picks.
Per-instance database work is capped at six active queries without a waiting
queue, with connection, statement and query timeouts. This instance cap is not
a global traffic limit.

Public API guards reject mutations, unknown or duplicate query parameters,
oversized/control-character input and cross-site browser reads before database
work, including forged prefetch headers. HTML uses a fresh nonce CSP, framing
denial and security headers. The unused public image optimizer is disabled.
Provider credentials are absent from the web deployment; its only configured
server credentials are the restricted database URL and public TLS CA.

The review included payout/refund and eligibility regressions, desktop/mobile
browser checks with real published research records, locally isolated eligible
fixtures, copy-time expiry checks, accessibility/overflow checks and bounded
HTTP security probes. Fixtures are never published as observed production bets.
Full frontend dependency audit found no known vulnerabilities. Backend tests,
dependency/static scans, migrations, PostgreSQL, worker isolation and all three
CodeQL analyses must pass on the exact PR head before merging.

A subsequent public-surface pass exercised 11 representative landing and
research states at desktop and mobile widths (22 route/viewport combinations).
It found no horizontal overflow, broken images, unnamed accessibility controls
or runtime exceptions. Disclosure, evidence-link and option controls now have
clear keyboard focus and larger touch targets while retaining native semantics.
The deployment verifier also requires the published retrospective evidence and
its limitation language, so a stale landing bundle cannot pass readiness.

Browser Fetch Metadata is accepted only for `same-origin` or direct navigation,
and a supplied `Origin` must match the request origin. Non-browser server clients
may omit both headers. Public archive offsets stop before 1,000 rows; game-log
player filters require normalized human-name characters and an explicit limit
of at most 200. Production readiness probes exercise these denial paths before
database reads and require rejection responses to be non-cacheable. All API
validation and availability errors explicitly use `Cache-Control: no-store`.
Responses also opt into an origin-keyed agent cluster and deny
legacy cross-domain policy files. The frontend production dependency audit,
backend environment audit and Bandit scan reported no known findings in this
pass; this remains point-in-time evidence rather than a guarantee.

These controls reduce abuse; **no public website is immune to DDoS**. Distributed
clients can evade a per-IP allowance, low-rate expensive requests can still
consume capacity, and platform/provider outages remain possible. Monitor Vercel
firewall activity, function/database failures and usage; configure account-level
spend alerts and review attack traffic before tightening challenges or limits.
Spending limits, a distributed load test and an external penetration test have
not been verified by this review. No production flood test or order execution
is performed.
