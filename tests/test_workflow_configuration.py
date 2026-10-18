from pathlib import Path
import re


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "data.yml"
PUBLIC_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "public-data.yml"
CI_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
PUBLIC_MONITOR_SCHEDULES = (
    "7 0,3,6,9,15,18,21 * * *", "37 1,4,7,10,16,19,22 * * *",
)
PUBLIC_DAILY_PRIMARY_SCHEDULE = "7 12 * * *"
PUBLIC_DAILY_RECOVERY_SCHEDULE = "37 13 * * *"
PAID_SCAN_SCHEDULES = (
    "19 0,16,20 * * 2-5", "19 0,16 * * 6", "55 23 * * 6",
    "35 15 * * 0", "45 18 * * 0",
    "19 0,16 * * 1", "45 22 * * 0,1",
)
NFL_HISTORY_RECOVERY_SCHEDULE = "29 10 * * 2,5"


def _schedules(source: str) -> set[str]:
    return set(re.findall(r"^\s+- cron: '([^']+)'$", source, re.MULTILINE))


def test_budgeted_public_slots_remain_distinct_and_ninety_minutes_apart() -> None:
    source = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    times = []
    for cron in _schedules(source):
        minute, hour, day, month, weekday = cron.split()
        assert (day, month, weekday) == ("*", "*", "*")
        times.extend(int(h) * 60 + int(minute) for h in hour.split(","))
    times.sort()
    assert len(times) == len(set(times)) == 16
    assert [((times[(i + 1) % 16] - times[i]) % 1440) for i in range(16)] == [90] * 16


def _paid_slots(weekday: int) -> set[int]:
    slots = {12 * 60 + 17}
    for cron in PAID_SCAN_SCHEDULES:
        minute, hours, day, month, weekdays = cron.split()
        assert (day, month) == ("*", "*")
        days = set(range(7)) if weekdays == "*" else set()
        if weekdays != "*":
            for part in weekdays.split(","):
                if "-" in part:
                    start, end = map(int, part.split("-"))
                    days.update(range(start, end + 1))
                else:
                    days.add(int(part))
        if weekday in days:
            slots.update(int(hour) * 60 + int(minute) for hour in hours.split(","))
    return slots


def test_paid_slots_cover_october_nfl_prelock_without_more_daily_jobs() -> None:
    # UTC kickoff groups from pinned 2026 week-four NFL schedule, SHA-256
    # 4f27270efeba3af862d250a821ff00578da1ce158b76576b72aa283751b22662.
    from datetime import datetime, timedelta, timezone

    assert all(len(_paid_slots(day)) == 4 for day in range(7))
    starts = [(datetime(2026, 10, 4, 13, 30, tzinfo=timezone.utc), 1),
              (datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc), 8),
              (datetime(2026, 10, 4, 20, 5, tzinfo=timezone.utc), 1),
              (datetime(2026, 10, 4, 20, 25, tzinfo=timezone.utc), 3),
              (datetime(2026, 10, 5, 0, 20, tzinfo=timezone.utc), 1),
              (datetime(2026, 10, 6, 0, 15, tzinfo=timezone.utc), 1)]
    covered = 0
    for kickoff, games in starts:
        times = [kickoff - timedelta(days=offset) for offset in (0, 1)]
        slots = [day.replace(hour=minute // 60, minute=minute % 60, second=0)
                 for day in times for minute in _paid_slots((day.weekday() + 1) % 7)]
        if any(kickoff - timedelta(hours=2) <= slot <= kickoff - timedelta(hours=1, minutes=10)
               for slot in slots):
            covered += games
    assert covered == 15
    # The retained public ESPN October 3 FBS response has the Fresno State at
    # Washington State game at 2026-10-04 01:30 UTC. Saturday's existing
    # third scan stays in its T-120 to T-70 prelock window after retiming.
    cfb_start = datetime(2026, 10, 4, 1, 30, tzinfo=timezone.utc)
    saturday = cfb_start - timedelta(days=1)
    saturday_slots = [saturday.replace(hour=minute // 60, minute=minute % 60,
                                        second=0) for minute in _paid_slots(6)]
    assert any(cfb_start - timedelta(hours=2) <= slot <= cfb_start - timedelta(hours=1, minutes=10)
               for slot in saturday_slots)


def _step(source: str, name: str) -> str:
    start = source.index(f"      - name: {name}")
    end = source.find("\n      - ", start + 1)
    return source[start:] if end == -1 else source[start:end]


def _job(source: str, name: str) -> str:
    start = re.search(rf"^  {re.escape(name)}:\s*$", source, re.MULTILINE)
    assert start is not None
    end = re.search(r"^  [a-z][a-z0-9-]*:\s*$", source[start.end():], re.MULTILINE)
    return source[start.start():] if end is None else source[start.start():start.end() + end.start()]


def _needs(job: str) -> set[str]:
    dependency_line = re.search(r"^    needs: \[(.*?)\]$", job, re.MULTILINE)
    assert dependency_line is not None
    return set(dependency_line.group(1).split(", "))


def test_paid_and_public_schedules_are_isolated() -> None:
    paid = WORKFLOW.read_text(encoding="utf-8")
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")

    assert _schedules(paid) == {
        "17 12 * * *", *PAID_SCAN_SCHEDULES, NFL_HISTORY_RECOVERY_SCHEDULE,
    }
    assert _schedules(public) == {
        *PUBLIC_MONITOR_SCHEDULES,
        PUBLIC_DAILY_PRIMARY_SCHEDULE,
        PUBLIC_DAILY_RECOVERY_SCHEDULE,
    }

    assert "vars.DATA_PIPELINE_ENABLED == 'true'" in paid
    assert "PAID_MONITOR_ENABLED" not in paid
    assert "github.event.schedule == '17 12 * * *'" in paid
    for schedule in PAID_SCAN_SCHEDULES:
        assert f"github.event.schedule == '{schedule}'" in paid
    assert "(vars.DATA_PIPELINE_ENABLED == 'true' && (" in paid
    assert f"github.event.schedule == '{NFL_HISTORY_RECOVERY_SCHEDULE}'" in paid
    assert "vars.DATA_PIPELINE_ENABLED == 'true' && 'scan' || 'monitor'" in paid
    assert "PUBLIC_DATA_PIPELINE_ENABLED" not in paid
    assert "vars.PUBLIC_DATA_PIPELINE_ENABLED == 'true'" in public
    assert "vars.DATA_PIPELINE_ENABLED" not in public
    assert "ODDS_API_KEY" not in public
    assert "group: market-data" in paid
    assert "group: public-market-data" in public

    paid_operation = next(line for line in paid.splitlines() if line.startswith("      OPERATION:"))
    assert "github.event.schedule == '17 12 * * *' && 'daily'" in paid_operation
    assert f"github.event.schedule == '{NFL_HISTORY_RECOVERY_SCHEDULE}' && 'refresh'" in paid_operation
    assert "vars.DATA_PIPELINE_ENABLED == 'true' && 'scan' || 'monitor'" in paid_operation
    assert f"github.event.schedule == '{NFL_HISTORY_RECOVERY_SCHEDULE}' && 'nfl'" in paid

    operation = next(line for line in public.splitlines() if line.startswith("      OPERATION:"))
    public_daily = (
        f"(github.event.schedule == '{PUBLIC_DAILY_PRIMARY_SCHEDULE}' || "
        f"github.event.schedule == '{PUBLIC_DAILY_RECOVERY_SCHEDULE}') && 'public_daily'"
    )
    assert public_daily in operation


def test_hosted_schema_is_migrated_after_ci_and_checked_before_collection_and_deploy() -> None:
    data = WORKFLOW.read_text(encoding="utf-8")
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    check = "uv run --locked alembic current --check-heads"
    assert data.index(check) < data.index("name: Collect live market data")
    assert public.index(check) < public.index("name: Update public market data")

    schema_job = _job(ci, "production-schema")
    assert _needs(schema_job) == {
        "release-inputs", "secrets", "backend", "frontend", "postgres", "worker-image",
    }
    # Only provisioning derives a writer from the dashboard identity; schema
    # readiness retains its existing worker read and separate owner migration.
    provision_step = _step(schema_job, "Provision and verify dedicated waitlist credential without rotation")
    assert "DATABASE_URL: ${{ secrets.DASHBOARD_DATABASE_URL }}" in provision_step
    assert "secrets.DATABASE_URL" not in provision_step
    assert "secrets.DASHBOARD_DATABASE_URL" not in schema_job.replace(provision_step, "")
    assert "DATABASE_URL: ${{ secrets.DATABASE_URL }}" in schema_job[:schema_job.index("    steps:")]
    for collection in (data, public):
        assert "secrets.DASHBOARD_DATABASE_URL" not in collection
        assert "secrets.DATABASE_URL" in collection
    sync = "uv sync --locked --only-group migrations"
    plan = "production-transaction-preflight.py --plan-schema"
    upgrade = ".venv/bin/alembic upgrade head"
    verify = "production-transaction-preflight.py --require-schema"
    probe = "run: .venv/bin/python .github/scripts/production-transaction-preflight.py\n"
    assert schema_job.index(sync) < schema_job.index(plan) < schema_job.index(upgrade)
    assert schema_job.index(upgrade) < schema_job.index(verify) < schema_job.index(probe)
    assert "uv run --locked alembic" not in schema_job

    postgres_job = ci[ci.index("  postgres:"):ci.index("  worker-image:")]
    assert sync in postgres_job
    assert "migrations-venv/bin/alembic\" current --check-heads" in postgres_job
    migration_step = _step(schema_job, "Apply reviewed migrations when hosted schema is behind")
    owner_check = _step(schema_job, "Verify owner migration credential is configured when required")
    verification_step = _step(schema_job, "Verify hosted schema is at the application head")
    for step in (owner_check, migration_step):
        assert "if: steps.schema.outputs.migration_needed == 'true'" in step
        assert "secrets.DATABASE_MIGRATION_URL" in step
    assert "secrets.DATABASE_MIGRATION_URL" not in verification_step
    assert "secrets.DATABASE_MIGRATION_URL" not in _step(
        schema_job, "Plan hosted schema using restricted transaction reader"
    )

    deploy_job = _job(ci, "deploy")
    assert _needs(deploy_job) == {
        "release-inputs", "secrets", "backend", "frontend", "postgres", "worker-image",
        "production-schema", "release-plan",
    }

def test_public_collection_verifies_the_deployed_contract_before_success() -> None:
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    update = "name: Update public market data"
    readiness = "name: Verify private access and published snapshot receipt"
    evidence = "name: Stage public evidence without configured provider credentials"

    assert public.index(update) < public.index(readiness) < public.index(evidence)
    assert '--report-output "$report_path"' in public
    assert '| tee ' not in _step(public, "Update public market data")
    assert "node frontend/scripts/verify-production.mjs" in public
    assert "DATA_PIPELINE_ENABLED: 'false'" in public
    assert "PUBLIC_DATA_PIPELINE_ENABLED: 'true'" in public
    assert "PUBLIC_DATA_REPORT_PATH: ${{ steps.public_update.outputs.report_path }}" in public
    verification = _step(public, "Verify private access and published snapshot receipt")
    assert verification.index('verify-published-snapshots.py') < verification.index('verify-production.mjs')
    assert 'PUBLIC_DATA_REPORT_PATH= node frontend/scripts/verify-production.mjs' in verification


def test_provider_credentials_are_scoped_to_the_steps_that_need_them() -> None:
    paid = WORKFLOW.read_text(encoding="utf-8")
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")

    assert "secrets." not in paid[:paid.index("    steps:")]
    assert "secrets." not in public[:public.index("    steps:")]

    for source, update, evidence in (
        (paid, "Collect live market data", "Stage public evidence without configured credentials"),
        (public, "Update public market data", "Stage public evidence without configured provider credentials"),
    ):
        assert "secrets.DATABASE_URL" in _step(source, "Check worker configuration")
        assert "secrets.DATABASE_URL" in _step(source, "Verify hosted schema is at the application head")
        assert "secrets.DATABASE_URL" in _step(source, update)
        assert "secrets.DATABASE_URL" in _step(source, evidence)
        assert "secrets." not in _step(source, "Install checksum-pinned secret scanner")
        assert "secrets." not in _step(source, "Scan public evidence")
        assert "secrets." not in _step(source, "Report local-only raw evidence")

    verification = _step(public, "Verify private access and published snapshot receipt")
    # A restricted receipt read replaces anonymous access to live snapshots.
    assert re.findall(r'secrets\.([A-Z_]+)', verification) == ['DATABASE_URL']
    assert 'OWNER_' not in verification and 'NEXTAUTH_' not in verification
    assert "secrets.ODDS_API_KEY" in _step(paid, "Collect live market data")
    assert "env.OPERATION == 'scan'" in _step(paid, "Collect live market data")
    assert "github.event_name == 'schedule'" not in _step(paid, "Collect live market data")
    assert "ODDS_API_KEY" not in public


def test_cfb_publication_has_an_independent_exact_receipt_gate_and_private_readiness() -> None:
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    update = _step(public, "Update CFB schedule without consuming odds credits")
    proof = _step(public, "Verify exact published CFB slate receipt")
    readiness = _step(public, "Verify private access and published snapshot receipt")
    assert 'id: cfb_schedule' in update
    assert '--sport cfb --report-output "$RUNNER_TEMP/cfb-slate-report.json"' in update
    assert "if: always() && !cancelled() && steps.cfb_schedule.outcome == 'success'" in proof
    assert 'PUBLIC_DATA_REPORT_PATH: ${{ runner.temp }}/cfb-slate-report.json' in proof
    assert 'verify-published-snapshots.py' in proof
    assert re.findall(r'secrets\.([A-Z_]+)', proof) == ['DATABASE_URL']
    assert public.index(update) < public.index(proof) < public.index(readiness)
    # CFB-only runs have no NFL/NBA report, but must still verify their slate
    # and the deployed owner-access contract. A proof failure is never ignored.
    assert "if: env.SPORT != 'cfb'" not in readiness
    assert 'if [ "$SPORT" != cfb ]; then' in readiness
    assert readiness.index('verify-published-snapshots.py') < readiness.index('fi\n')
    assert readiness.index('fi\n') < readiness.index('node frontend/scripts/verify-production.mjs')
    assert 'continue-on-error' not in proof


def test_public_profiles_and_validated_receipts_survive_independent_degradation() -> None:
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    update = _step(public, "Update public market data")
    readiness = _step(public, "Verify private access and published snapshot receipt")
    settlement = _step(public, "Settle CFB from free final sources")
    assert 'id: public_update' in update
    prerequisites = (
        "if: always() && !cancelled() && steps.worker_config.outcome == 'success' "
        "&& steps.schema.outcome == 'success' && "
    )
    readiness_guard = re.search(r'^\s*(if: .+)$', readiness, re.MULTILINE)
    # Explicit status functions avoid the implicit success() that previously
    # skipped these independent operations after degraded CFB settlement.
    assert readiness_guard is not None and readiness_guard.group(1) == prerequisites + (
        "((env.SPORT != 'cfb' && steps.public_update.outputs.report_ready == 'true') "
        "|| (env.SPORT == 'cfb' && steps.cfb_schedule.outcome == 'success'))"
    )
    # Profile work now runs promptly inside the producer and is included in its
    # validated report, before unrelated histories/settlements can age inputs.
    # A late standalone call would duplicate roster collection.
    assert 'python -m sportsbet.player_profiles' not in public
    assert 'second roster refresh here would duplicate' in public
    # A validated report survives intentional producer exit 2 and preserves
    # independent publication verification after degraded CFB settlement.
    assert 'public_update.outcome' not in readiness_guard.group(1)
    assert 'mktemp -d "$RUNNER_TEMP/public-report.XXXXXXXX"' in update
    assert 'started_at="$(date -u' in update and 'status=$?' in update
    assert 'if [ "$status" -eq 0 ] || [ "$status" -eq 2 ]; then' in update
    assert 'if ! uv run --locked python .github/scripts/validate-public-report.py' in update
    assert update.index('validate-public-report.py') < update.index('report_ready=true')
    assert 'if [ "$status" -eq 0 ]; then exit 1; fi' in update
    assert update.rstrip().endswith('exit "$status"')
    assert 'continue-on-error' not in update
    # CFB-only runs skip the absent NFL/NBA report and retain site access checks.
    assert 'if [ "$SPORT" != cfb ]; then' in readiness
    assert 'PUBLIC_DATA_REPORT_PATH= node frontend/scripts/verify-production.mjs' in readiness
    for step in (readiness, settlement):
        assert 'continue-on-error' not in step
    assert 'python -m sportsbet.cfb_public_settlement' in settlement


def test_paid_collection_reports_degraded_coverage_without_masking_fatal_errors() -> None:
    paid = WORKFLOW.read_text(encoding="utf-8")
    step = _step(paid, "Collect live market data")

    assert "status=$?" in step
    assert 'if [ "$status" -eq 2 ]' in step
    assert "::warning title=Live data coverage is degraded::" in step
    assert '>> "$GITHUB_STEP_SUMMARY"' in step
    assert 'exit "$status"' in step


def test_paid_schedule_collects_all_three_sports_and_keeps_public_modes_separate() -> None:
    paid = WORKFLOW.read_text(encoding="utf-8")
    configuration = _step(paid, "Check worker configuration")
    profiles = _step(paid, "Update source-backed player profiles")
    assert "options: [both, all, nfl, nba, cfb]" in paid
    assert "github.event.schedule == '17 12 * * *' || vars.DATA_PIPELINE_ENABLED == 'true') && 'all'" in paid
    assert f"github.event.schedule == '{NFL_HISTORY_RECOVERY_SCHEDULE}' && 'nfl'" in paid
    assert '[ "$SPORT" = all ] && [ "$OPERATION" != daily ] && [ "$OPERATION" != monitor ] && [ "$OPERATION" != scan ]' in configuration
    assert '[ "$OPERATION" != daily ] && [ "$OPERATION" != monitor ]; then' in configuration
    assert 'if [ "$SPORT" = all ]; then profile_sport=both; fi' in profiles
    assert "if: env.SPORT != 'cfb'" in profiles
    assert "env.SPORT == 'all' || env.SPORT == 'nfl'" in paid


def test_release_planning_cannot_skip_live_checks_or_mutate_from_a_review_branch() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    schema = _job(ci, "production-schema")
    plan = _job(ci, "release-plan")
    deploy = _job(ci, "deploy")
    production_guard = "github.ref == 'refs/heads/master' && (github.event_name == 'push' || inputs.force_frontend_deploy == true)"
    assert production_guard in deploy
    assert "github.ref == 'refs/heads/master' && (github.event_name == 'push' || inputs.force_frontend_deploy == true || (" in schema
    assert "github.event_name == 'workflow_dispatch' && inputs.public_landing_only == true && inputs.force_frontend_deploy != true && github.repository_id == '1199906339' && github.actor_id == '76501505'" in schema
    assert "default: false" in ci[ci.index("  workflow_dispatch:"):ci.index("permissions:")]
    assert "fetch-depth: 0" in plan and "persist-credentials: false" in plan
    assert "node .github/scripts/deployment-plan.mjs" in plan
    assert "vercel deploy" not in plan and "DATABASE_MIGRATION_URL" not in plan
    assert "github.ref == 'refs/heads/master' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')" in plan
    assert _needs(plan) == {
        "release-inputs", "secrets", "backend", "frontend", "postgres", "worker-image",
    }
    assert "inputs.public_landing_only" not in deploy
    assert "FORCE_FRONTEND_DEPLOY: ${{ inputs.force_frontend_deploy || false }}" in plan
    assert "PUBLIC_LANDING_ONLY" not in plan
    conditional = "      - if: needs.release-plan.outputs.deploy == 'true'"
    assert deploy.count(conditional) == 2
    verify = _step(deploy, "Verify unchanged deployed access controls and data readiness")
    assert "if: needs.release-plan.outputs.deploy != 'true'" in verify
    assert "node frontend/scripts/verify-production.mjs" in verify
    preflight = _step(deploy, "Attest auth settings and enforce private containment before deployment")
    transition = _step(deploy, "Transition reviewed deployment from containment to owner authentication")
    for step in (preflight, transition):
        assert "if: needs.release-plan.outputs.deploy == 'true'" in step
    assert 'private-dashboard-release.mjs preflight' in preflight
    assert 'private-dashboard-release.mjs finish' in transition
    assert deploy.index('private-dashboard-release.mjs preflight') < deploy.index('vercel deploy')
    assert deploy.index('vercel deploy') < deploy.index('private-dashboard-release.mjs finish')
    recovery = _step(deploy, "Recover privacy containment after interruption")
    assert '(failure() || cancelled())' in recovery
    assert 'private-dashboard-release.mjs recover' in recovery
    assert '--meta sportsbetCommit="$GITHUB_SHA"' in deploy


def test_vercel_token_is_unavailable_to_checkout_install_and_public_verification() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    plan = _job(ci, "release-plan")
    deploy = _job(ci, "deploy")
    for job in (plan, deploy):
        assert "secrets.VERCEL_TOKEN" not in job[:job.index("    steps:")]
    assert "secrets.VERCEL_TOKEN" in _step(plan, "Compare current source with the live production deployment")
    assert "secrets.VERCEL_TOKEN" not in _step(deploy, "Verify unchanged deployed access controls and data readiness")
    installer = deploy[deploy.index("      - if:"):deploy.index("      # Only create")]
    assert "npm install" in installer and "secrets.VERCEL_TOKEN" not in installer


def test_public_landing_input_is_off_by_default_and_validated_before_production_secrets() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    dispatch = ci[ci.index("  workflow_dispatch:"):ci.index("permissions:")]
    for name in ("force_frontend_deploy", "public_landing_only"):
        match = re.search(rf"^      {name}:\n(.*?)(?=^      [a-z_]+:|\Z)", dispatch, re.MULTILINE | re.DOTALL)
        assert match is not None
        assert "        type: boolean" in match.group(1)
        assert "        default: false" in match.group(1)
    gate = _job(ci, "release-inputs")
    assert "    if:" not in gate and "    needs:" not in gate
    assert "    permissions: {}" in gate
    assert "environment:" not in gate and "secrets." not in gate and "uses:" not in gate
    assert "PUBLIC_LANDING_ONLY: ${{ inputs.public_landing_only || false }}" in gate
    assert "FORCE_FRONTEND_DEPLOY: ${{ inputs.force_frontend_deploy || false }}" in gate
    validation = _step(gate, "Validate mutually exclusive release inputs and public scope")
    assert 'case "$PUBLIC_LANDING_ONLY:$FORCE_FRONTEND_DEPLOY" in' in validation
    assert "false:false|false:true|true:false) ;;" in validation
    assert "true:true)" not in validation
    assert "Invalid or conflicting release inputs'; exit 1" in validation
    assert 'if [[ "$PUBLIC_LANDING_ONLY" == true ]]; then' in validation
    for condition in (
        '"$GITHUB_EVENT_NAME" != workflow_dispatch',
        '"$GITHUB_REF" != refs/heads/master',
        '"$GITHUB_REPOSITORY_ID" != 1199906339',
        '"$GITHUB_ACTOR_ID" != 76501505',
    ):
        assert condition in validation
    assert "${{" not in validation
    for name in ("production-schema", "release-plan", "deploy", "deploy-public-contained"):
        job = _job(ci, name)
        assert "release-inputs" in _needs(job)
        assert "always()" not in job
        assert "environment: production" in job


def test_public_landing_release_is_manual_owner_scoped_and_keeps_all_real_code_gates() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    job = _job(ci, "deploy-public-contained")
    assert "    if: github.event_name == 'workflow_dispatch' && inputs.public_landing_only == true && inputs.force_frontend_deploy != true && github.ref == 'refs/heads/master' && github.repository_id == '1199906339' && github.actor_id == '76501505'\n" in job
    assert _needs(job) == {
        "release-inputs", "secrets", "backend", "frontend", "postgres", "worker-image",
        "production-schema", "release-plan",
    }
    assert "    runs-on: ubuntu-latest" in job
    assert "    timeout-minutes: 15" in job
    assert "    environment: production" in job
    permissions = job[job.index("    permissions:"):job.index("    env:")]
    assert permissions.strip() == "permissions:\n      contents: read\n      checks: read\n      actions: read\n      pull-requests: read"
    assert "persist-credentials: false" in job and "node-version: '24'" in job
    assert "VERCEL_ORG_ID: ${{ vars.VERCEL_ORG_ID }}" in job
    assert "VERCEL_PROJECT_ID: ${{ vars.VERCEL_PROJECT_ID }}" in job
    assert "CONTAINED_PUBLIC_RECEIPT: ${{ runner.temp }}/contained-public-release.json" in job
    assert "PUBLIC_LANDING_ONLY: ${{ inputs.public_landing_only }}" in job
    assert "FORCE_FRONTEND_DEPLOY: ${{ inputs.force_frontend_deploy || false }}" in job
    before_steps = job[:job.index("    steps:")]
    assert "secrets." not in before_steps and "GITHUB_TOKEN:" not in before_steps
    install = _step(job, "Install pinned Vercel CLI without release credentials")
    preflight = _step(job, "Verify contained public release prerequisites")
    deploy = _step(job, "Deploy public landing with private containment retained")
    finish = _step(job, "Verify deployed public landing and retained private containment")
    assert "run: npm install --global vercel@59.15.1" in install
    assert "secrets." not in install
    assert "secrets." not in job[job.index("    steps:"):job.index(install)]
    for step, operation in ((preflight, "preflight"), (finish, "finish")):
        assert "VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}" in step
        assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in step
        assert f"run: node .github/scripts/contained-public-release.mjs {operation}" in step
    assert "VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}" in deploy
    assert "GITHUB_TOKEN" not in deploy
    assert 'run: vercel deploy --yes --prod --force --meta sportsbetCommit="$GITHUB_SHA" --token="$VERCEL_TOKEN"' in deploy
    assert job.index(install) < job.index(preflight) < job.index(deploy) < job.index(finish)
    for forbidden in (
        "private-dashboard-release.mjs", " recover", "firewall", "PRODUCTION_VERIFY_ATTEMPTS",
        "continue-on-error", "cancelled()", "failure()", "retry", "needs.release-plan.outputs.deploy",
    ):
        assert forbidden not in job
