"""Migration tests (DATA-04).

Tests verify that alembic upgrade head creates all 5 tables and that
alembic downgrade base removes them cleanly.

Marked @pytest.mark.serial to prevent concurrent DB state corruption.
Skipped automatically when SPORTSBET_TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
import hashlib
import json

import pytest
import sqlalchemy as sa
import alembic.command
import alembic.config


def get_alembic_cfg(url: str) -> alembic.config.Config:
    """Build an Alembic Config with the given DB URL."""
    cfg = alembic.config.Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.mark.serial
@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable database required')
def test_browser_role_migration_closes_owner_view_and_preserves_data():
    url = os.environ['SPORTSBET_TEST_DATABASE_URL']
    cfg = get_alembic_cfg(url)
    alembic.command.upgrade(cfg, '0023_worker_snapshot_append')
    engine = sa.create_engine(url)
    created = []
    try:
        with engine.begin() as conn:
            for role in ('anon', 'authenticated'):
                if not conn.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}).first():
                    conn.execute(sa.text(f'CREATE ROLE {role} NOLOGIN'))
                    created.append(role)
                conn.execute(sa.text(f'GRANT ALL ON public.dashboard_snapshots, public.dashboard_gamelogs TO {role}'))
                for schema in ('public','analytics'):
                    for kind in ('TABLES','SEQUENCES'):
                        conn.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON {kind} TO {role}'))
            for schema in ('public','analytics'):
                for kind in ('TABLES','SEQUENCES'):
                    conn.execute(sa.text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON {kind} TO PUBLIC'))
            conn.execute(sa.text("INSERT INTO dashboard_snapshots(snapshot_key,payload) VALUES ('acl-proof','{}')"))
        alembic.command.upgrade(cfg, 'head')
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM dashboard_snapshots WHERE snapshot_key='acl-proof'")).scalar_one() == 1
            for role in ('anon', 'authenticated'):
                assert not conn.execute(sa.text("SELECT has_function_privilege(:role,"
                    "'analytics.stamp_prediction_record()','EXECUTE')"), {'role':role}).scalar_one()
                for table in ('public.dashboard_snapshots', 'public.dashboard_gamelogs', 'public.dashboard_gamelogs_asof',
                              'public.provider_response_cache', 'public.ngs_stats',
                              'public.cfb_history_source_bundles', 'public.cfb_receiving_supplements',
                              'public.cfb_primary_revisions',
                              'public.cfb_effective_gamelogs', 'public.nfl_history_source_bundles',
                              'public.nfl_receiving_supplements', 'public.nfl_effective_receiving_gamelogs',
                              'analytics.paper_selections', 'analytics.prospective_audit_reports'):
                    assert not conn.execute(sa.text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"),
                                            {'role': role, 'table': table}).scalar_one()
        for role in ('anon', 'authenticated'):
            with pytest.raises(sa.exc.ProgrammingError):
                with engine.begin() as conn:
                    conn.execute(sa.text(f'SET LOCAL ROLE {role}'))
                    conn.execute(sa.text('SELECT * FROM public.dashboard_gamelogs_asof LIMIT 1'))
        alembic.command.downgrade(cfg, '0023_worker_snapshot_append')
        with engine.connect() as conn:
            assert not conn.execute(sa.text("SELECT has_table_privilege('anon','public.dashboard_gamelogs','SELECT')")).scalar_one()
        # Verify defaults remain closed even after downgrade, without RLS masking grants.
        with engine.begin() as conn:
            for schema in ('public','analytics'):
                conn.execute(sa.text(f'CREATE TABLE {schema}.browser_default_probe(id SERIAL PRIMARY KEY)'))
                conn.execute(sa.text(f'INSERT INTO {schema}.browser_default_probe DEFAULT VALUES'))
                conn.execute(sa.text(f'CREATE VIEW {schema}.browser_default_view AS SELECT * FROM {schema}.browser_default_probe'))
                for role in ('anon','authenticated'):
                    for table in ('browser_default_probe','browser_default_view'):
                        assert not conn.execute(sa.text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"),
                                                {'role':role,'table':f'{schema}.{table}'}).scalar_one()
                    assert not conn.execute(sa.text("SELECT has_sequence_privilege(:role,pg_get_serial_sequence(:table,'id'),'USAGE,SELECT,UPDATE')"),
                                            {'role':role,'table':f'{schema}.browser_default_probe'}).scalar_one()
        for role in ('anon','authenticated'):
            with pytest.raises(sa.exc.ProgrammingError):
                with engine.begin() as conn:
                    conn.execute(sa.text(f'SET LOCAL ROLE {role}'))
                    conn.execute(sa.text('SELECT * FROM public.browser_default_view'))
    finally:
        with engine.begin() as conn:
            for schema in ('public','analytics'):
                conn.execute(sa.text(f'DROP VIEW IF EXISTS {schema}.browser_default_view'))
                conn.execute(sa.text(f'DROP TABLE IF EXISTS {schema}.browser_default_probe'))
        alembic.command.downgrade(cfg, 'base')
        with engine.begin() as conn:
            for role in created:
                conn.execute(sa.text(f'DROP ROLE {role}'))
        engine.dispose()


@pytest.mark.serial
@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable database required')
def test_ngs_migration_replaces_preexisting_worker_policy():
    url = os.environ['SPORTSBET_TEST_DATABASE_URL']
    cfg = get_alembic_cfg(url)
    engine = sa.create_engine(url)
    created_role = False
    try:
        with engine.begin() as conn:
            if not conn.execute(sa.text(
                "SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker'"
            )).first():
                conn.execute(sa.text('CREATE ROLE sportsbet_worker NOLOGIN'))
                created_role = True
        # Grant the restricted role access as each historical table is created.
        alembic.command.upgrade(cfg, '0028_cfb_player_gamelogs')
        with engine.begin() as conn:
            conn.execute(sa.text('ALTER TABLE ngs_stats ENABLE ROW LEVEL SECURITY'))
            conn.execute(sa.text("""CREATE POLICY sportsbet_worker_read ON ngs_stats
                FOR SELECT TO sportsbet_worker USING (true)"""))
        with engine.begin() as conn:
            conn.execute(sa.text('GRANT DELETE ON analytics.predictions TO sportsbet_worker'))
        alembic.command.upgrade(cfg, 'head')
        with engine.connect() as conn:
            assert not conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',"
                "'analytics.predictions','DELETE')")).scalar_one()
            policies = conn.execute(sa.text("""SELECT policyname FROM pg_policies
                WHERE schemaname='public' AND tablename='ngs_stats'
                  AND policyname LIKE 'sportsbet_worker_%'""")).scalars().all()
        assert set(policies) == {
            'sportsbet_worker_read', 'sportsbet_worker_insert',
            'sportsbet_worker_update', 'sportsbet_worker_delete',
        }
        from tests.test_cfb_history_completeness import primary
        row=primary();row['game_id']=str(row['game_id'])
        with engine.begin() as conn:
            assert conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',"
                "'public.cfb_primary_revisions','SELECT,INSERT')")).scalar_one()
            assert conn.execute(sa.text("SELECT has_sequence_privilege('sportsbet_worker',"
                "'public.cfb_primary_revisions_revision_id_seq','USAGE,SELECT')")).scalar_one()
            conn.execute(sa.text('INSERT INTO public.cfb_player_gamelogs ('+','.join(row)+') VALUES ('
                +','.join(':'+name for name in row)+')'),row)
        with engine.begin() as conn:
            conn.execute(sa.text('SET LOCAL ROLE sportsbet_worker'))
            result=conn.execute(sa.text('UPDATE public.cfb_player_gamelogs SET rushing_yards=69 '
                'WHERE athlete_id=:athlete AND game_id=:game'),
                {'athlete':row['athlete_id'],'game':row['game_id']})
            assert result.rowcount==1
        with engine.connect() as conn:
            assert conn.execute(sa.text('SELECT count(*) FROM public.cfb_primary_revisions '
                'WHERE athlete_id=:athlete AND game_id=:game'),
                {'athlete':row['athlete_id'],'game':row['game_id']}).scalar_one()==1
        # Private prospective reports must be insertable by the restricted worker,
        # but neither browsable nor mutable by dashboard roles.
        report={'protocol':{'version':'nfl-receiving-individual-pick-audit-v1'},
                'observed_at':'2026-10-01T13:00:00+00:00','promote':False,'target_verified':False}
        payload=json.dumps(report,sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(payload.encode()).hexdigest()
        with engine.begin() as conn:
            assert conn.execute(sa.text("SELECT has_schema_privilege('sportsbet_worker',"
                "'analytics','USAGE')" )).scalar_one()
            assert conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',"
                "'analytics.prospective_audit_reports','SELECT,INSERT')")).scalar_one()
            assert not conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',"
                "'analytics.prospective_audit_reports','UPDATE,DELETE,TRUNCATE')")).scalar_one()
            assert conn.execute(sa.text("SELECT has_sequence_privilege('sportsbet_worker',"
                "'analytics.prospective_audit_reports_report_id_seq','USAGE,SELECT')")).scalar_one()
            conn.execute(sa.text('SET LOCAL ROLE sportsbet_worker'))
            inserted=conn.execute(sa.text('''INSERT INTO analytics.prospective_audit_reports
                (protocol,observed_at,recorded_at,payload,payload_sha256)
                VALUES (:protocol,:observed,:forged,:payload,:digest)
                RETURNING report_id,recorded_at'''),
                {'protocol':'nfl-receiving-individual-pick-audit-v1',
                 'observed':report['observed_at'],'forged':'2000-01-01T00:00:00Z',
                 'payload':payload,'digest':digest}).one()
            assert inserted.recorded_at.year >= 2026
            assert conn.execute(sa.text('SELECT count(*) FROM analytics.prospective_audit_reports')).scalar_one()==1
        priced={'protocol':{'version':'nfl-priced-prospective-checkpoint-v1'},
                'observed_at':'2026-10-02T00:00:00+00:00',
                'assessment':{'status':'insufficient_data'},
                'promote':False,'target_verified':False}
        priced_payload=json.dumps(priced,sort_keys=True,separators=(',',':'))
        with engine.begin() as conn:
            conn.execute(sa.text('SET LOCAL ROLE sportsbet_worker'))
            conn.execute(sa.text('''INSERT INTO analytics.prospective_audit_reports
                (protocol,observed_at,payload,payload_sha256)
                VALUES (:protocol,:observed,:payload,:digest)'''),
                {'protocol':'nfl-priced-prospective-checkpoint-v1',
                 'observed':priced['observed_at'],'payload':priced_payload,
                 'digest':hashlib.sha256(priced_payload.encode()).hexdigest()})
            assert conn.execute(sa.text('SELECT count(*) FROM analytics.prospective_audit_reports')).scalar_one()==2
        current={'protocol':{'version':'nfl-history-priced-prospective-v1'},
                 'observed_at':'2026-10-02T00:00:00+00:00',
                 'assessment':{'status':'insufficient_data'},
                 'promote':False,'target_verified':False}
        current_payload=json.dumps(current,sort_keys=True,separators=(',',':'))
        with engine.begin() as conn:
            conn.execute(sa.text('SET LOCAL ROLE sportsbet_worker'))
            conn.execute(sa.text('''INSERT INTO analytics.prospective_audit_reports
                (protocol,observed_at,payload,payload_sha256)
                VALUES (:protocol,:observed,:payload,:digest)'''),
                {'protocol':'nfl-history-priced-prospective-v1',
                 'observed':current['observed_at'],'payload':current_payload,
                 'digest':hashlib.sha256(current_payload.encode()).hexdigest()})
            assert conn.execute(sa.text('SELECT count(*) FROM analytics.prospective_audit_reports')).scalar_one()==3
        # The downgrade must refuse retained priced reports; this disposable test
        # removes its own row with the owner role before the ordinary teardown.
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM analytics.prospective_audit_reports "
                                 "WHERE protocol IN ('nfl-priced-prospective-checkpoint-v1',"
                                 "'nfl-history-priced-prospective-v1')"))
    finally:
        alembic.command.downgrade(cfg, 'base')
        if created_role:
            with engine.begin() as conn:
                conn.execute(sa.text('DROP ROLE sportsbet_worker'))
        engine.dispose()


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_alembic_upgrade_clean() -> None:
    """alembic upgrade head must run cleanly on a fresh PostgreSQL instance.

    Asserts all 7 tables exist after upgrade (5 original + 2 Phase 10 prop/NBA).
    Runs downgrade as cleanup.
    """
    url = os.environ["SPORTSBET_TEST_DATABASE_URL"]
    cfg = get_alembic_cfg(url)
    alembic.command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    with engine.connect():
        tables = sa.inspect(engine).get_table_names()
    assert "games" in tables, "games table missing after upgrade head"
    assert "play_by_play" in tables, "play_by_play table missing after upgrade head"
    assert "player_stats" in tables, "player_stats table missing after upgrade head"
    assert "nfl_snap_counts" in tables, "nfl_snap_counts table missing after upgrade head"
    assert "ngs_stats" in tables, "ngs_stats table missing after upgrade head"
    assert "odds_snapshots" in tables, "odds_snapshots table missing after upgrade head"
    assert "player_prop_snapshots" in tables, "player_prop_snapshots table missing after upgrade head"
    assert "nba_player_stats" in tables, "nba_player_stats table missing after upgrade head"
    assert "provider_response_cache" in tables, "provider response cache missing after upgrade head"
    assert "cfb_player_gamelogs" in tables, "CFB player game logs missing after upgrade head"
    ngs_columns = {column['name'] for column in sa.inspect(engine).get_columns('ngs_stats')}
    assert {'avg_intended_air_yards','passer_rating','attempts','avg_yac','catch_percentage',
            'targets','receptions','percent_attempts_gte_eight_defenders','rush_attempts',
            'source_provider','source_url','source_sha256','source_record_sha256',
            'source_observed_at'} <= ngs_columns
    # Cleanup ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â leave DB clean for next test run
    alembic.command.downgrade(cfg, "base")


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_alembic_downgrade_clean() -> None:
    """alembic downgrade base must cleanly remove all tables.

    Runs upgrade first, then downgrade, then asserts tables are gone.
    """
    url = os.environ["SPORTSBET_TEST_DATABASE_URL"]
    cfg = get_alembic_cfg(url)
    alembic.command.upgrade(cfg, "head")
    alembic.command.downgrade(cfg, "base")
    engine = sa.create_engine(url)
    tables = sa.inspect(engine).get_table_names()
    assert "games" not in tables, "games table still present after downgrade base"
    assert "play_by_play" not in tables, "play_by_play still present after downgrade base"
    assert "player_stats" not in tables, "player_stats still present after downgrade base"
    assert "nfl_snap_counts" not in tables, "nfl_snap_counts still present after downgrade base"
    assert "ngs_stats" not in tables, "ngs_stats still present after downgrade base"
    assert "odds_snapshots" not in tables, "odds_snapshots still present after downgrade base"
    assert "player_prop_snapshots" not in tables, "player_prop_snapshots still present after downgrade base"
    assert "nba_player_stats" not in tables, "nba_player_stats still present after downgrade base"
    assert "cfb_player_gamelogs" not in tables, "CFB player game logs still present after downgrade base"


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_prop_table_indexes_exist() -> None:
    """Three composite indexes on player_prop_snapshots must exist after upgrade head.

    Uses pg_indexes system catalog to verify index names, which are only present
    after alembic upgrade head succeeds on a live PostgreSQL instance.
    """
    url = os.environ["SPORTSBET_TEST_DATABASE_URL"]
    cfg = get_alembic_cfg(url)
    alembic.command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'player_prop_snapshots'"
            )
        ).fetchall()
        index_names = {row[0] for row in rows}

    assert "idx_props_player_prop_snapped" in index_names, (
        "idx_props_player_prop_snapped missing from player_prop_snapshots"
    )
    assert "idx_props_sport_snapped" in index_names, (
        "idx_props_sport_snapped missing from player_prop_snapshots"
    )
    assert "idx_props_game_prop" in index_names, (
        "idx_props_game_prop missing from player_prop_snapshots"
    )
    # Cleanup
    alembic.command.downgrade(cfg, "base")


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_new_prop_quote_constraint_preserves_legacy_rows_and_rejects_bad_inserts() -> None:
    """The unvalidated constraint protects new rows without rewriting legacy evidence."""
    url = os.environ["SPORTSBET_TEST_DATABASE_URL"]
    cfg = get_alembic_cfg(url)
    alembic.command.upgrade(cfg, "0013_nba_stat_provenance")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            INSERT INTO player_prop_snapshots
                (sport, player_name, sportsbook, prop_type, implied_probability)
            VALUES ('nba', 'Legacy Player', 'legacy', 'player_points', 0.5)
        """))
    alembic.command.upgrade(cfg, "head")
    with engine.begin() as conn:
        validated = conn.execute(sa.text("""
            SELECT convalidated FROM pg_constraint
            WHERE conname = 'ck_player_prop_snapshots_complete_quote'
        """)).scalar_one()
        assert validated is False
        assert conn.execute(sa.text(
            "SELECT COUNT(*) FROM player_prop_snapshots WHERE sportsbook='legacy'"
        )).scalar_one() == 1
        conn.execute(sa.text("""
            INSERT INTO player_prop_snapshots
                (sport, game_id, player_name, sportsbook, prop_type, line, price,
                 implied_probability, side, snapped_at, game_start_time, source_provider,
                 source_sha256, source_record_sha256)
            VALUES ('nfl', 'event', 'Player', 'book', 'player_pass_yds', 249.5,
                    -110, 0.523809, 'Over', '2026-09-12T00:00:00Z',
                    '2026-09-13T00:00:00Z', 'the_odds_api',
                    :source, :record)
        """), {'source':'a'*64, 'record':'b'*64})
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO player_prop_snapshots
                    (sport, player_name, sportsbook, prop_type, implied_probability)
                VALUES ('nba', 'New Invalid Player', 'book', 'player_points', 0.5)
            """))
    with engine.connect() as conn:
        assert conn.execute(sa.text("""
            SELECT convalidated FROM pg_constraint
            WHERE conname = 'ck_player_prop_snapshots_source_evidence'
        """)).scalar_one() is False
    alembic.command.downgrade(cfg, "0013_nba_stat_provenance")
    with engine.connect() as conn:
        assert conn.execute(sa.text("""
            SELECT COUNT(*) FROM pg_constraint
            WHERE conname = 'ck_player_prop_snapshots_complete_quote'
        """)).scalar_one() == 0
    engine.dispose()
    alembic.command.downgrade(cfg, "base")


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_settlement_constraint_preserves_legacy_and_requires_new_provenance() -> None:
    """Old outcomes remain evidence; every future settlement identifies its source."""
    from sportsbet.ledger import Ledger

    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    alembic.command.upgrade(cfg,'0014_prop_snapshot_integrity')
    engine=sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO analytics.predictions(id,scan_id,payload,outcome) VALUES ('legacy','s','{}','true')"))
    alembic.command.upgrade(cfg,'head')
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT outcome FROM analytics.predictions WHERE id='legacy'")).scalar_one()=='true'
        assert conn.execute(sa.text("SELECT convalidated FROM pg_constraint WHERE conname='ck_prediction_settlement_evidence'")).scalar_one() is False
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO analytics.predictions(id,scan_id,payload) VALUES ('new','s','{}')"))
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE analytics.predictions SET outcome='true' WHERE id='new'"))
    Ledger(database_url=url).settle({'new':True})
    with engine.connect() as conn:
        row=conn.execute(sa.text("SELECT outcome,outcome_source,outcome_ref,outcome_observed_at FROM analytics.predictions WHERE id='new'")).one()
        assert tuple(row[:3])==('true','manual','caller_supplied') and row[3] is not None
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE analytics.predictions SET actual_value=-1 WHERE id='new'"))
        assert conn.execute(sa.text("SELECT actual_value FROM analytics.predictions WHERE id='new'" )).scalar_one()==-1
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE analytics.predictions SET actual_value='NaN' WHERE id='new'"))
    engine.dispose();alembic.command.downgrade(cfg,'base')


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_stat_source_constraints_preserve_legacy_and_require_new_evidence() -> None:
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    alembic.command.upgrade(cfg,'0015_settlement_provenance')
    engine=sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO player_stats(player_id,season,week) VALUES ('legacy',2025,1)"))
        conn.execute(sa.text("INSERT INTO nba_player_gamelogs(player_id,game_id,season) VALUES (1,'legacy',2025)"))
    alembic.command.upgrade(cfg,'head')
    with engine.connect() as conn:
        for name in ('ck_player_stats_source_evidence','ck_nba_gamelog_source_evidence'):
            assert conn.execute(sa.text('SELECT convalidated FROM pg_constraint WHERE conname=:name'),
                {'name':name}).scalar_one() is False
        assert conn.execute(sa.text("SELECT count(*) FROM player_stats WHERE player_id='legacy'" )).scalar_one()==1
        assert conn.execute(sa.text("SELECT count(*) FROM nba_player_gamelogs WHERE game_id='legacy'" )).scalar_one()==1
    with engine.begin() as conn:
        conn.execute(sa.text("""INSERT INTO player_stats(player_id,season,week,source_provider,
            source_sha256,source_record_sha256,source_observed_at)
            VALUES ('valid',2025,1,'nflverse',:hash,:hash,NOW())"""),{'hash':'a'*64})
        conn.execute(sa.text("""INSERT INTO nba_player_gamelogs(player_id,game_id,season,source_provider,
            source_sha256,source_record_sha256,source_observed_at)
            VALUES (2,'valid',2025,'nba',:hash,:hash,NOW())"""),{'hash':'b'*64})
    for statement in (
        "INSERT INTO player_stats(player_id,season,week) VALUES ('invalid',2025,1)",
        "INSERT INTO nba_player_gamelogs(player_id,game_id,season) VALUES (3,'invalid',2025)",
        """INSERT INTO player_stats(player_id,season,week,source_provider,source_sha256,source_observed_at)
            VALUES ('missing-record-hash',2025,1,'nflverse',repeat('a',64),NOW())""",
        """INSERT INTO nba_player_gamelogs(player_id,game_id,season,source_provider,source_sha256,source_observed_at)
            VALUES (3,'missing-record-hash',2025,'nba',repeat('b',64),NOW())""",
    ):
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(sa.text(statement))
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE player_stats SET week=2 WHERE player_id='legacy'"))
    alembic.command.downgrade(cfg,'0015_settlement_provenance')
    columns={column['name'] for column in sa.inspect(engine).get_columns('player_stats')}
    assert not {'source_provider','source_sha256','source_record_sha256','source_observed_at'} & columns
    engine.dispose();alembic.command.downgrade(cfg,'base')


@pytest.mark.serial
@pytest.mark.skipif(
    not os.environ.get("SPORTSBET_TEST_DATABASE_URL"),
    reason="SPORTSBET_TEST_DATABASE_URL not set",
)
def test_verified_settlement_evidence_constraint_preserves_legacy_rows() -> None:
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    alembic.command.upgrade(cfg,'0019_prop_quote_provenance')
    engine=sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("""INSERT INTO analytics.predictions
            (id,scan_id,payload,outcome,outcome_source,outcome_ref,outcome_observed_at)
            VALUES ('legacy-proof','s','{}','true','observed_final_stats','legacy',NOW())"""))
    alembic.command.upgrade(cfg,'head')
    with engine.connect() as conn:
        row=conn.execute(sa.text("""SELECT outcome,outcome_evidence FROM analytics.predictions
            WHERE id='legacy-proof'""")).one()
        assert tuple(row)==('true',None)
        assert conn.execute(sa.text("""SELECT convalidated FROM pg_constraint
            WHERE conname='ck_verified_settlement_evidence'""")).scalar_one() is False
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(sa.text("""UPDATE analytics.predictions SET outcome='false'
                WHERE id='legacy-proof'"""))
    with pytest.raises(sa.exc.DataError):
        with engine.begin() as conn:
            conn.execute(sa.text("""UPDATE analytics.predictions SET outcome='false',
                outcome_evidence='invalid-json' WHERE id='legacy-proof'"""))
    with engine.begin() as conn:
        conn.execute(sa.text("""UPDATE analytics.predictions SET outcome='false',outcome_evidence='{}'
            WHERE id='legacy-proof'"""))
    alembic.command.downgrade(cfg,'0019_prop_quote_provenance')
    with engine.connect() as conn:
        assert 'outcome_evidence' not in {
            column['name'] for column in sa.inspect(engine).get_columns('predictions',schema='analytics')}
    engine.dispose();alembic.command.downgrade(cfg,'base')


@pytest.mark.serial
@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable database required')
def test_gamelog_identity_view_preserves_rows_and_security_on_upgrade_and_downgrade():
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    alembic.command.upgrade(cfg,'0029_ngs_evidence');engine=sa.create_engine(url)
    with engine.begin() as conn:
        for player,points in [(101,9),(102,30)]:
            conn.execute(sa.text("""INSERT INTO nba_player_gamelogs
                (player_id,game_id,season,game_date,player_name,team_abbreviation,opponent_team,points,
                 source_provider,source_sha256,source_record_sha256,source_observed_at)
                VALUES (:player,'same-game',2025,'2026-01-01','Same Name','BOS','NYK',:points,
                    'nba',repeat('a',64),repeat('b',64),NOW())"""),dict(player=player,points=points))
        conn.execute(sa.text("INSERT INTO games(game_id,season,week,home_team,away_team,game_date) VALUES ('id-game',2026,1,'BUF','NYJ','2026-09-10')"))
        conn.execute(sa.text("""INSERT INTO player_stats(player_id,player_name,season,week,team,receptions,
            source_provider,source_sha256,source_record_sha256,source_observed_at)
            VALUES ('00-0000001','NFL Player',2026,1,'BUF',4,'nflverse',repeat('a',64),repeat('b',64),NOW())"""))
        conn.execute(sa.text("""INSERT INTO cfb_player_gamelogs(athlete_id,game_id,season,week,game_date,
            player_name,team_id,team_name,team_abbreviation,opponent_id,opponent_name,opponent_abbreviation,
            is_home,receiving_yards,source_provider,source_sha256,source_player_sha256,source_schedule_sha256,
            source_record_sha256,source_observed_at)
            VALUES (201,'cfb-game',2026,1,'2026-09-10','CFB Player',1,'Home','HOM',2,'Away','AWY',true,50,
                'sportsdataverse_espn',repeat('a',64),repeat('b',64),repeat('c',64),repeat('d',64),NOW())"""))
    try:
        alembic.command.upgrade(cfg,'head')
        with engine.connect() as conn:
            rows=conn.execute(sa.text('SELECT sport,player_id,payload FROM dashboard_gamelogs ORDER BY sport,player_id')).all()
            assert len(rows)==4
            assert all(payload['player_id']==player for _,player,payload in rows)
            assert conn.execute(sa.text("SELECT payload->>'points' FROM dashboard_gamelogs WHERE sport='nba' AND player_id='101'")).scalar_one()=='9'
            assert conn.execute(sa.text("SELECT reloptions FROM pg_class WHERE oid='public.dashboard_gamelogs'::regclass")).scalar_one()==['security_barrier=true']
            assert not conn.execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a WHERE c.oid='public.dashboard_gamelogs'::regclass AND a.grantee=0)")).scalar_one()
        alembic.command.downgrade(cfg,'0029_ngs_evidence')
        with engine.connect() as conn:
            assert conn.execute(sa.text('SELECT count(*) FROM dashboard_gamelogs')).scalar_one()==4
            assert 'player_id' not in {c['name'] for c in sa.inspect(conn).get_columns('dashboard_gamelogs')}
            assert all('player_id' not in row[0] for row in conn.execute(sa.text('SELECT payload FROM dashboard_gamelogs')))
        alembic.command.upgrade(cfg,'head')
        with engine.connect() as conn:
            assert conn.execute(sa.text('SELECT count(*) FROM dashboard_gamelogs WHERE player_id IS NOT NULL')).scalar_one()==4
    finally:
        engine.dispose();alembic.command.downgrade(cfg,'base')


@pytest.mark.serial
@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable database required')
def test_cfb_supplements_are_append_only_and_view_is_restricted():
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    alembic.command.upgrade(cfg,'0030_gamelog_player_identity')
    engine=sa.create_engine(url)
    created=[]
    try:
        with engine.begin() as conn:
            for role in ('sportsbet_worker','sportsbet_dashboard','anon','authenticated'):
                if not conn.execute(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
                    conn.execute(sa.text(f'CREATE ROLE {role} NOLOGIN'));created.append(role)
        alembic.command.upgrade(cfg,'head')
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT reloptions FROM pg_class WHERE oid='public.cfb_effective_gamelogs'::regclass")).scalar_one()==['security_barrier=true']
            for table in ('cfb_history_source_bundles','cfb_receiving_supplements'):
                assert conn.execute(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)"),{'table':'public.'+table}).scalar_one()
                for permission in ('SELECT','INSERT'):
                    assert conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',:table,:permission)"),{'table':'public.'+table,'permission':permission}).scalar_one()
                for permission in ('UPDATE','DELETE','TRUNCATE'):
                    assert not conn.execute(sa.text("SELECT has_table_privilege('sportsbet_worker',:table,:permission)"),{'table':'public.'+table,'permission':permission}).scalar_one()
            for role in ('sportsbet_dashboard','anon','authenticated'):
                for target in ('cfb_history_source_bundles','cfb_receiving_supplements','cfb_effective_gamelogs'):
                    assert not conn.execute(sa.text("SELECT has_table_privilege(:role,:target,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"),{'role':role,'target':'public.'+target}).scalar_one()
        alembic.command.downgrade(cfg,'0030_gamelog_player_identity')
        alembic.command.upgrade(cfg,'head')
    finally:
        with engine.begin() as conn:
            for role in created:
                conn.execute(sa.text(f'DROP OWNED BY {role}'));conn.execute(sa.text(f'DROP ROLE {role}'))
        engine.dispose()


@pytest.mark.serial
@pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'), reason='Disposable database required')
def test_prediction_record_receipts_are_database_owned():
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'];cfg=get_alembic_cfg(url)
    engine=sa.create_engine(url)
    try:
        alembic.command.downgrade(cfg,'base')
        alembic.command.upgrade(cfg,'0038_private_prospective_reports')
        with engine.begin() as conn:
            columns={column['name'] for column in sa.inspect(conn).get_columns('predictions',schema='analytics')}
            assert 'recorded_at' not in columns and 'payload_sha256' not in columns
            conn.execute(sa.text("INSERT INTO analytics.predictions(id,scan_id,payload) VALUES ('legacy','old','{}')"))
        alembic.command.upgrade(cfg,'head')
        with engine.begin() as conn:
            legacy=conn.execute(sa.text("SELECT recorded_at,payload_sha256 FROM analytics.predictions WHERE id='legacy'")).one()
            assert legacy == (None,None)
            recorded,digest=conn.execute(sa.text("""INSERT INTO analytics.predictions
                (id,scan_id,payload,recorded_at,payload_sha256)
                VALUES ('new','scan','{}','2000-01-01T00:00:00Z',repeat('0',64))
                RETURNING recorded_at,payload_sha256""")).one()
            assert recorded.year >= 2026
            assert digest == hashlib.sha256(b'{}').hexdigest()
            assert conn.execute(sa.text("UPDATE analytics.predictions SET outcome_evidence='{}' WHERE id='new'")).rowcount == 1
        for statement in (
            "UPDATE analytics.predictions SET payload='changed' WHERE id='new'",
            "UPDATE analytics.predictions SET recorded_at='2000-01-01T00:00:00Z' WHERE id='new'",
        ):
            with pytest.raises(sa.exc.DBAPIError):
                with engine.begin() as conn:
                    conn.execute(sa.text(statement))
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT payload FROM analytics.predictions WHERE id='new'")).scalar_one() == '{}'
        alembic.command.downgrade(cfg,'0038_private_prospective_reports')
        with engine.connect() as conn:
            columns={column['name'] for column in sa.inspect(conn).get_columns('predictions',schema='analytics')}
            assert 'recorded_at' not in columns and 'payload_sha256' not in columns
    finally:
        alembic.command.downgrade(cfg,'base')
        engine.dispose()
