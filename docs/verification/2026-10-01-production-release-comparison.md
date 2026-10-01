# Compare releases with the live frontend

Research-only master commits previously created an unchanged Vercel deployment.
The free deployment quota was exhausted. The release plan now resolves the
production hostname through the authenticated Vercel API and verifies project,
READY/production status and one consistent commit identity. It compares that
commit with the current checkout, rather than comparing consecutive commits.
An earlier undeployed frontend change therefore remains pending on a later
research-only commit.

Compared paths include the entire frontend, upload boundary and root workspace
configuration. Unknown identities, missing Git objects, non-ancestor commits or
metadata read failures stop the plan; they never turn into an automatic skip or
an unverified deployment attempt. Provider bodies and secrets are not logged.
No plans upgrade an account or retry an exhausted deployment quota.

All test/security/container/schema gates remain. The deploy job still runs the
existing live access-control/data-readiness verification when it reuses the live
frontend. CLI installation and deployment are conditional on a proven source
change. New deployments include an explicit commit metadata field.

This is source comparison. Changes made directly to Vercel environment/build
settings require the explicit master-only `force_frontend_deploy` workflow input.
A default manual run only inspects the release plan and cannot deploy. Review-branch
manual runs can validate authenticated read-only planning before merge; production
mutations remain master-only. Project root changes are rejected.

Verification covers source equality, a pending frontend release followed by a
research commit, upload-boundary changes, explicit redeploy, invalid/conflicting
metadata, API errors, missing Git history and bounded read-only provider requests.
An integration test creates actual Git commits to verify the comparison.

API reference: [Get a deployment by ID or URL](https://vercel.com/docs/rest-api/deployments/get-a-deployment-by-id-or-url).
