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

    schema_job = ci[ci.index("  production-schema:"):ci.index("  release-plan:")]
    assert "needs: [secrets, backend, frontend, postgres, worker-image]" in schema_job
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

    deploy_job = ci[ci.index("\n  deploy:\n"):]
    dependency_line = re.search(r"^    needs: \[(.*?)\]$", deploy_job, re.MULTILINE)
    assert dependency_line is not None
    assert set(dependency_line.group(1).split(", ")) == {
        "secrets", "backend", "frontend", "postgres", "worker-image", "production-schema", "release-plan",
    }

def test_public_collection_verifies_the_deployed_contract_before_success() -> None:
    public = PUBLIC_WORKFLOW.read_text(encoding="utf-8")
    update = "name: Update public market data"
    readiness = "name: Verify deployed public readiness"
    evidence = "name: Stage public evidence without configured provider credentials"

    assert public.index(update) < public.index(readiness) < public.index(evidence)
    assert '--report-output "$RUNNER_TEMP/public-report.json"' in public
    assert '| tee ' not in _step(public, "Update public market data")
    assert "node frontend/scripts/verify-production.mjs" in public
    assert "DATA_PIPELINE_ENABLED: 'false'" in public
    assert "PUBLIC_DATA_PIPELINE_ENABLED: 'true'" in public
    assert "PUBLIC_DATA_REPORT_PATH: ${{ runner.temp }}/public-report.json" in public


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
        assert "secrets." not in _step(source, "Retain public market evidence for replay")

    assert "secrets." not in _step(public, "Verify deployed public readiness")
    assert "secrets.ODDS_API_KEY" in _step(paid, "Collect live market data")
    assert "env.OPERATION == 'scan'" in _step(paid, "Collect live market data")
    assert "github.event_name == 'schedule'" not in _step(paid, "Collect live market data")
    assert "ODDS_API_KEY" not in public


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
    schema = ci[ci.index("  production-schema:"):ci.index("  release-plan:")]
    plan = ci[ci.index("  release-plan:"):ci.index("\n  deploy:\n")]
    deploy = ci[ci.index("\n  deploy:\n"):]
    production_guard = "github.ref == 'refs/heads/master' && (github.event_name == 'push' || inputs.force_frontend_deploy == true)"
    assert production_guard in schema and production_guard in deploy
    assert "default: false" in ci[ci.index("  workflow_dispatch:"):ci.index("permissions:")]
    assert "fetch-depth: 0" in plan and "persist-credentials: false" in plan
    assert "node .github/scripts/deployment-plan.mjs" in plan
    assert "vercel deploy" not in plan and "DATABASE_MIGRATION_URL" not in plan
    assert "github.ref == 'refs/heads/master' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')" in plan
    assert "needs: [secrets, backend, frontend, postgres, worker-image]" in plan
    conditional = "      - if: needs.release-plan.outputs.deploy == 'true'"
    assert deploy.count(conditional) == 2
    verify = _step(deploy, "Verify deployed access controls and data readiness")
    assert "if:" not in verify and "node frontend/scripts/verify-production.mjs" in verify
    assert '--meta sportsbetCommit="$GITHUB_SHA"' in deploy


def test_vercel_token_is_unavailable_to_checkout_install_and_public_verification() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    plan = ci[ci.index("  release-plan:"):ci.index("\n  deploy:\n")]
    deploy = ci[ci.index("\n  deploy:\n"):]
    for job in (plan, deploy):
        assert "secrets.VERCEL_TOKEN" not in job[:job.index("    steps:")]
    assert "secrets.VERCEL_TOKEN" in _step(plan, "Compare current source with the live production deployment")
    assert "secrets.VERCEL_TOKEN" not in _step(deploy, "Verify deployed access controls and data readiness")
    installer = deploy[deploy.index("      - if:"):deploy.index("      # Only create")]
    assert "npm install" in installer and "secrets.VERCEL_TOKEN" not in installer
