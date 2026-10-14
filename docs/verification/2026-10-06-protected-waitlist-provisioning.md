# Protected waitlist credential provisioning

## Concrete release gap repaired

The previous release referenced a credential provisioner that did not exist.
`ops/provision_waitlist.py` now creates and verifies the dedicated writer using
existing protected migration credentials and publishes its URL only as a
Vercel production **sensitive** setting. No extra credential needs to be pasted
into chat or committed. This is reviewed release code, not production execution.

The existing `production-schema` job runs it after migration-head verification
and the restricted transaction reader probe. That job still requires the five
existing test gates and the protected production environment; deployment still
requires all seven existing dependencies. The account/CI and private CodeQL
blocks are retained. No budget, reserve, collector, model or evaluation changes.

## Boundary and sequence

1. Refuse execution outside a valid master Actions context. Pin the existing
   project/team, Hobby plan and frontend root. No plan change or purchase API.
2. Require exactly one verified TLS mode and reject driver option overrides.
   Match the owner/reader host, database and Supabase project reference. Derive
   the writer username and transaction-pool port; never reuse owner credentials.
3. Require the reviewed `0046_private_waitlist` schema head. Create only a new
   LOGIN with NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION and
   NOBYPASSRLS. Generate a 48-byte random password and encrypt it with SCRAM on
   the client before SQL execution. Plaintext is never placed in SQL logs.
4. Grant only schema USAGE and execution of `join_waitlist(text)`. Check effective
   table, column, view and sequence privileges, schema/database creation,
   ownership and both membership directions. PostgreSQL 16's administrative
   grant to the trusted creator is allowed only with neither SET nor INHERIT.
   PUBLIC privilege drift fails rather than changing unrelated database grants.
5. Verify the exact reviewed function body, fixed search path, SECURITY DEFINER,
   boolean result and owner distinct from the writer. Reject access to other
   privileged application functions. Ordinary PUBLIC invoker functions and
   PostgreSQL's default CONNECT/TEMP privileges are not globally revoked.
6. Commit, authenticate with the actual generated password through the writer
   connection, execute the signup function and roll back the test entry AND
   rate-limit counters. A bounded false/rate-limit result is valid. No retained
   fake signup or consent record is produced.
7. Recheck absence of the environment key, then use a single create-only API
   request. Target production only; no upsert/PATCH/DELETE/secret-decryption
   path exists. Read back metadata, bind its digest to the role's provenance
   comment and recheck privileges. URLs, passwords, response bodies and tokens
   are never printed or persisted to local files.

## Reruns and limitations

An existing managed production secret/role pair is checked for matching
provenance and current effective privileges. Its sensitive value cannot be
read back, so a rerun does **not** claim a fresh password-authentication check.
It never rotates or republishes that credential. Real production waitlist
persistence remains an activation acceptance item.

An existing unmanaged role, mismatched setting or missing pair fails closed.
The script never repurposes a dashboard/worker/provider role. There is no global
privilege repair, credential rotation, role deletion or environment overwrite.
A lost publication acknowledgement is reconciled on the next run if metadata
matches the already verified new login. A failure/crash after role commit but
before a confirmed secret leaves a narrowly privileged orphan and requires
operator reconciliation. The next run refuses to rotate it automatically.
GitHub cancellation and provider outage are not treated as successful setup.

The owner migration credential must support CREATEROLE and grants; no attempt
is made to raise its privileges. Only PostgreSQL 16+ membership semantics are
supported by this release gate. Different provider connection identities stop
setup instead of assuming that two owners share a database.

## Verification

- Final focused PostgreSQL/provisioner suite: **61 passed** (60 new checks plus
  the existing waitlist ACL/retention regression). The full migration-chain
  compatibility case is included. The local test runner disabled unrelated
  conftest/plugins; its single warning concerns the unused asyncio setting.
- Private release/owner checks: **66 passed**, plus all **five** production
  readiness checks passed separately. The initial command used a nonexistent
  readiness filename; the correctly named file was then run explicitly.
- Cached Bandit security scan passed on the new production script.
- Workflow YAML parsed; all job identities, production environments,
  dependencies, master conditions, permissions and deployment steps retained.
  The only existing-step changes broaden backend Bandit and PostgreSQL coverage.
  No continue-on-error or gate bypass was added. Actionlint was not available.
- Live read-only inspection: five provider GETs, zero mutations; containment
  remains active at version 2, no diagnostic exception active, unrelated digest
  unchanged. OAuth client settings and WAITLIST_DATABASE_URL are still missing.
  The latter is now provisioned by reviewed code after the protected gates,
  rather than requiring a separate manual credential copy.
- Staged redacted Gitleaks scan passed (48.80 KB, no leaks). The exact fixture
  container identity was checked before removal; other containers were untouched.
Tests use an explicitly loopback-only disposable PostgreSQL 16 container and
simulated provider responses. They include actual SCRAM password acceptance
and wrong-password rejection, rollback of signups/counters, full application
migration compatibility, non-superuser role creation, PUBLIC/column/sequence
and role privilege drift, function tampering, repeatability, interrupted
publication, no-rotation refusals, free-plan identity, redirect refusal,
create-only sensitive publication and redacted CLI errors.

No production DDL, environment write, deployment, quote collection or purchase
was executed for this work. Existing containment remains in effect. OAuth
configuration and required CI/account/security gates still precede activation.

## Original alpha evidence checkpoint

Frozen model/evaluation definitions and private anchors remain unchanged.
The next independent pregame checkpoint is **October 8, 17:25 UTC / 10:25 AM
Pacific**: capture/publisher exit, source/schedule/receiving-integrity/recent-gap
receipts and a private server-dated anchor before kickoff. Missing chronology
cannot be repaired after games. No edge, 75% performance or consumer pick
promotion is established by this infrastructure change.

## Primary references

- [PostgreSQL role creation](https://www.postgresql.org/docs/16/sql-createrole.html)
- [PostgreSQL effective privilege functions](https://www.postgresql.org/docs/16/functions-info.html)
- [Vercel environment creation API](https://vercel.com/docs/rest-api/projects/create-one-or-more-environment-variables)
- [Vercel environment metadata API](https://vercel.com/docs/rest-api/projects/retrieve-the-environment-variables-of-a-project-by-id-or-name)
