# October 6: contained owner-authentication release transition

## Failure addressed

Emergency privacy containment correctly returns 403 for the old public dashboard.
The previous production preflight required old live reads, while the final private
verifier requires app-generated 401 and login redirects. Removing the deny rule
before testing the replacement would expose an unverified release. That transition
was missing from the deployment job.

## Implemented protected flow

The existing production job still requires secrets, backend, frontend, PostgreSQL,
worker-image, production-schema and release-plan success and its protected production
environment. Every other job, branch condition, permission and concurrency setting
is unchanged. No continue-on-error or protection override is added.

1. Read the pinned project's production metadata and existing **Hobby** team plan.
   Require one unbranched production entry for NEXTAUTH_URL, NEXTAUTH_SECRET,
   GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and WAITLIST_DATABASE_URL. Values are
   not logged or written to a receipt.
2. Attest the exact active containment policy and real denied paths. Later upgrades
   of an already-private release first run the complete app verifier and reinstate
   the same public deny before the production replacement. The existing schema
   job continues to verify the actual restricted database read; HTTP 403 is not
   substituted for a successful database probe.
3. Deploy through the existing pinned Vercel CLI. Require READY production metadata,
   the pinned project/root, and the exact reviewed commit with no conflicting SHA.
   Check public UI/security headers, owner login, secure CSRF cookies and the sole
   GitHub provider while the old deny is still active.
4. Persist an atomic pending recovery receipt containing only validated commit,
   project, team and status fields. Insert a temporary deny rule with a fresh 256-bit
   diagnostic header exception before changing the original rule. Every original
   protected condition group retains a default public deny. The third rule fits the
   existing free three-rule allowance; unavailable capacity stops the transition.
5. A new nondata root canary is outside the old rule. Require missing/wrong diagnostic
   headers to get 403 and the exact header to get 404 before removing the original
   rule. This tests the real provider's missing-header semantics without exposing
   a previously protected data path.
6. With the diagnostic deny still protecting public requests, run the complete
   access verifier. The header only passes this temporary firewall condition;
   anonymous app APIs must still return the exact no-store 401 and the terminal
   must redirect to login. The real owner-access library ignores this header.
   Forward it only to the fixed production origin, with manual redirects and a
   bounded verification deadline. Never send an owner cookie or provider token
   to the public app verifier.
7. Reattest commit and unrelated firewall configuration, remove only the diagnostic
   rule, rerun the complete verifier without the header, and attest unchanged
   independent firewall settings again. Only then mark the receipt verified.
8. On failure or ambiguous provider mutation, reinsert the original deny before
   removing a known diagnostic rule. Reconcile insertion timeouts instead of
   blindly repeating writes. Failure/cancellation recovery consumes only a
   matching pending workflow receipt; stale or foreign receipts fail validation.
   A subsequent release preflight also repairs a known leftover diagnostic state.

All firewall updates are targeted inserts/removals of free custom deny rules. The
existing rate rule, managed-rule settings, IP rules and other controls are not
rewritten. Provider refusal/capacity limits do not lead to an upgrade or purchase.
A hard runner or provider outage can prevent recovery; the pending receipt and
known diagnostic default deny preserve a reviewable recovery checkpoint. Unknown
or malformed control-plane rules require operator review and are never silently
removed. A failed unchanged-source release can remain intentionally contained;
once prerequisites are restored, use the existing protected force_frontend_deploy
input for the reviewed rebuild rather than bypassing verification.

## Verification

- **71 focused checks passed:** all release-script checks, actual owner-cookie
  regressions and complete production-access verifier tests. The new controller
  cases cover source/project/plan/configuration drift, free capacity, canary
  semantics, cookie-only owner admission, every phase of the scoped transition,
  exposed app responses behind public containment, deadline expiry, ambiguous
  insert/remove outcomes, recovery failure, foreign asset origins and receipt
  identity. Provider mutations were simulated; no live diagnostic rule was created.
- Workflow YAML parsed. Comparing the previous tracked workflow proved every
  other job and all existing deployment needs/branch/environment/permission gates
  unchanged. Changed owner-test lint and the staged redacted Gitleaks scan passed.
- The existing final UI/build and 32 local HTTP checks from the owner-access
  increment are retained evidence. No broad backend/frontend build rerun is
  claimed for these deployment-script-only changes.

## Authoritative live check

Five **GET-only** provider requests revalidated the actual free project and active
privacy policy. A wrapper refused any mutating request. Active version remains
**2**, original containment is active, and no diagnostic rule exists. The unrelated
settings digest is
`26fc1843c606fbe3e743f3e05c77390da64dcfac94b890c0766f936ffc9399b8`.
Production readiness fails specifically for missing GITHUB_CLIENT_ID,
GITHUB_CLIENT_SECRET and WAITLIST_DATABASE_URL. No production deployment,
firewall change, database provisioning, quote collection, paid request or order
was made by this increment.

Private hosted CI is still rejected before runner startup by the account gate.
Required CodeQL and production protections remain. The release is not live and
real owner/second-account OAuth acceptance is still unverified. Waitlist writer
provisioning requires the reviewed schema release and least-privilege checks;
a configured key name alone does not prove durable production persistence.

## Research scope and next checkpoint

No model, evaluation version, prospective membership, qualified-pick threshold,
20-credit daily/450-credit rolling cap or staged pregame reserve changed. No win-rate
or market-alpha claim is promoted. Preserve both private frozen anchors. Next
prospective checkpoint remains **October 8 17:25 UTC / 10:25 AM Pacific**: verify
pregame capture/source/context receipts and its private server-dated anchor before
kickoff, then wait for the original result gate. Do not repeat the recovered
October 4 result collector.

## Provider references

- [Vercel targeted firewall API](https://vercel.com/docs/rest-api/security/update-firewall-configuration)
- [Vercel active firewall configuration](https://vercel.com/docs/rest-api/security/read-firewall-configuration)
- [Custom-rule execution](https://vercel.com/docs/vercel-firewall/vercel-waf/custom-rules)
- [Hobby custom-rule limits](https://vercel.com/docs/vercel-firewall/vercel-waf)
- [Free custom rules and priced features](https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing)
