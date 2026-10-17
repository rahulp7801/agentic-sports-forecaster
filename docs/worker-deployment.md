# Python worker deployment

Vercel continues to serve the read-only frontend. `Dockerfile.worker` packages the existing Python CLI and LangGraph computation for a separate container scheduler. It introduces no second model implementation, web server, custom cron loop, or order endpoint.

The current GitHub schedule has produced successful runs but also multi-hour gaps. An active workflow and one successful automatic run do not prove reliable cadence. GitHub documents that scheduled jobs can be [delayed or dropped under load](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Keep the dashboard's freshness gates enabled.

## Image contract

- Immutable official Python and uv image digests; runtime dependencies resolved from `uv.lock` with `--locked`, no editable install or development dependencies.
- Non-root UID/GID `10001`; package files are root-owned. Public database CA included. Source checkout, frontend, Git history and credentials are absent from the final image.
- Default-deny `.dockerignore` admits only the packaging files, named Python package directories, Python source and public CA. Add new package directories explicitly. CI injects harmless secret-shaped files and tests the actual Docker build context excludes them.
- `.local/` is the working evidence/cache directory. Supply durable private storage at `/app/.local` when captures must survive container replacement. The image does not upload arbitrary files or expose this directory over HTTP.
- Runtime needs outbound HTTPS to the supported public providers and verified PostgreSQL connectivity. No listening port is needed.
- CI runs the final image with networking disabled, a read-only root filesystem, dropped capabilities and writable temporary evidence storage. It imports the real CLIs and executes the actual LangGraph/SciPy solver on an explicitly synthetic arithmetic fixture. This test is not a provider test or return estimate.

```sh
docker build --file Dockerfile.worker --tag sportsbet-worker:reviewed .
docker run --rm --init --cap-drop ALL --security-opt no-new-privileges \
  --env-file /secure/worker.env \
  --mount type=bind,src=/secure/worker-evidence,dst=/app/.local \
  sportsbet-worker:reviewed
```

Provision the private evidence directory for UID/GID `10001` before starting the container. Do not mount the repository or the development `.env`. Set only the restricted **sportsbet_worker** connection strings:

| Variable | Required value |
| --- | --- |
| `DATABASE_URL` | Worker synchronous URL with verified TLS and `sslrootcert=certs/supabase-prod-ca-2021.crt` |
| `DATABASE_URL_ASYNC` | Matching worker asynchronous URL |
| `ANALYTICS_DATABASE_URL` | Same restricted synchronous URL, to prevent local SQLite fallback |
| `EXPERIMENTAL_PROBABILITY_ADJUSTMENTS` | `false` |

No Odds API or Kalshi trading credential is required for public-only operation. Do not supply the development owner credentials. The previously exposed Odds key must remain unused; full-provider activation requires verified replacement and provider readiness.

Protected-`master` CI applies reviewed Alembic migrations only after its test, security, PostgreSQL, and worker-image gates pass. The owner/DDL connection is stored separately as the production environment secret `DATABASE_MIGRATION_URL` and is scoped only to the migration step. CI then returns to restricted `DATABASE_URL` to verify the exact head before deploying Vercel. The worker receives read-only access to `public.alembic_version` so scheduled collection can run the same check; it has no schema-change privilege and stops before application work when that check fails.

## Scheduled commands and cutover

The default command performs one `public_monitor` run for both sports and exits. Configure the host to run it periodically; successful completion does not leave a daemon running. A separate daily command refreshes history as well:

```sh
python -m sportsbet.daily --mode public_monitor --sport both
python -m sportsbet.daily --mode public_daily --sport both
```

Use one active scheduler and serialize the two commands. Do not independently run two scheduler services that can overlap. On an existing server, one OS scheduler with a common process lock can supervise both. Configure bounded execution time, failure notifications and private evidence retention. These obligations are not implemented by a Docker image alone.

Within one paid event scan, the worker resolves each distinct player identity once
and runs at most eight independent selection graphs concurrently against the
ten-connection database pool. The event retains deterministic selection order and
does not write any model decision to the ledger until every graph invocation has
returned without an error state. Coverage reports unique and resolved players,
model requests, and the concurrency limit. This reduces avoidable serial work while
keeping database demand bounded; provider requests and separate events remain
serialized by the existing credit and event timeout controls.

Scan health separates observed quotes, distinct selections, model requests and
usable model estimates. A quoted event is model-complete only when every selection
has a resolved player and a usable estimate. Partial or unavailable model coverage
degrades the run and the published prop screen; an event timeout retains the quote
coverage already observed instead of turning it into an unexplained zero. A valid
empty slate and an event with no usable provider quotes remain separate states.

Cut over only after a hosted public monitor and daily refresh both pass, their archives replay, production matches the captures, and an automatic host-triggered run is observed. Then unset `PUBLIC_DATA_PIPELINE_ENABLED` in GitHub to stop duplicate scheduled collection; keep manual Actions runs available for recovery. Keep `DATA_PIPELINE_ENABLED` off until full-provider readiness is verified. Roll back by disabling the new schedule before restoring the public GitHub flag.

## Inspect provider configuration without collecting quotes

The manual **Read-only provider readiness** workflow runs only from this
repository's protected `master`, using the existing production worker database
and Odds API key. It shares the paid worker's concurrency group, has no schedule,
and does not enable `DATA_PIPELINE_ENABLED`.

The CLI is also available on an existing configured worker:

```sh
python -m sportsbet.provider_readiness --daily-credit-limit 20
```

It requires explicit `ANALYTICS_DATABASE_URL` and rejects the historically
exposed key before database or provider access. It reads the hosted credit ledger
in a read-only transaction and makes at most one bounded sports-list request.
The provider documents [`GET /v4/sports/`](https://the-odds-api.com/liveapi/guides/v4/#get-sports)
as consuming zero usage credits and returning the remaining, used and last-call
cost headers. The probe requires valid usage headers and a last-call cost of zero.
It collects no odds, reserves no credits, writes no cache or database rows, and
uploads no files. Provider bodies, authenticated URLs and credentials are never
included in its report or failure messages.

A successful observation establishes only the recorded key acceptance, sport
metadata, provider allowance and local ledger totals at that time. It does not
verify free-plan or billing status, future prop coverage, event-specific pregame
reserve availability, or permission to activate collection. Keep the existing
20-credit daily and 450-credit rolling caps and all scan qualification gates.
Unavailable configuration, provider evidence or ledger data remains explicit;
do not use another collection operation as a substitute for this probe.

## Verify completed degraded public captures

A public collector can finish, publish its partial observations and write its
final report while returning exit code 2 for incomplete coverage. The workflow
keeps that failure and validates the completed report before allowing its exact
database receipt check. Each invocation uses a fresh report path; malformed,
stale, wrong-scope or unfinished reports cannot enable verification. Fatal
collector failures remain failures. Verification reads the captured identities
without collecting prices again.

The daily profile worker reads its own bounded stored signal identities after
configuration and schema checks pass. It can run when a market source degrades;
empty inputs retain the original profile capture and timestamps.

Kalshi summaries retain bounded categorical failure diagnostics for the next
scheduled capture. They expose controlled stages, error categories and HTTP
status counts without provider bodies, authenticated URLs, player or event IDs.
Source status, partial coverage, accepted payloads, model outputs and qualification
rules retain their existing meaning. A verified publication receipt establishes
the identity of a stored capture; it does not establish complete coverage or an
edge.

When an individually linked prop fails quote validation, the collector can still
validate the remaining markets on that already received page. It retains only
quotes that pass the existing identity, chronology, price and settlement-rule
checks. That series remains invalid and incomplete, the overall capture remains
degraded, and the collector does not follow that page's cursor. Corrupt page,
market-identity and duplicate-market evidence retain their immediate aborts.
This does not add market-page or order-book requests. Retained valid quotes can
enable the existing single bulk player-target metadata read; missing target
evidence remains an explicit failure. Controlled validation reasons distinguish
the existing rejection conditions without retaining rejected provider payloads.

Kalshi's [official Market schema](https://docs.kalshi.com/openapi.yaml) defines
`primary_participant_key` as optional and nullable. The adapter accepts an absent
or null value while retaining the required custom player/team UUIDs, exact game
and team binding, and bulk player-target type, league and team verification.
A present conflicting value, including an empty string or a non-string value,
is rejected. Price, strike, settlement-rule and chronology checks still apply;
missing or conflicting target evidence keeps the handoff incomplete. Supporting
this documented shape does not establish which participant value a prior
rejected response contained or prove that live NBA coverage has recovered.

## Hosting decision remains open

No new service, billing plan or credential transfer has been activated by this change. A portable image can run on an existing server or a managed container host. As a possible managed option, [Render cron jobs](https://render.com/docs/cronjobs) support Docker and prevent overlap within one job; that guarantee does not serialize two separate jobs. Render currently bills for active compute with a $1/month minimum **per cron service**, plus any applicable workspace/platform charges. A continuously running background worker has different costs. Confirm the selected design and total cost before activation.

CI validates image behavior; actual host startup, scheduling, resource usage, durable evidence storage and provider connectivity must still be verified after a host is selected. No continuous monitoring or deployment readiness is inferred from a successful image build.
