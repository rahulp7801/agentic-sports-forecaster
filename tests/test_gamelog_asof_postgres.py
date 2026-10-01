"""As-of public projection uses real observation time and restricted grants."""
import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('SPORTSBET_TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required')


def test_nba_asof_projection_excludes_later_source_and_retains_public_payload():
    import psycopg
    url=os.environ['SPORTSBET_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    observed=datetime(2026,9,29,12,tzinfo=timezone.utc)
    with psycopg.connect(url) as conn:
        try:
            conn.execute("""INSERT INTO public.nba_player_gamelogs
                (player_id,player_name,team_abbreviation,game_id,game_date,season,
                 is_home,opponent_team,points,source_provider,source_sha256,
                 source_record_sha256,source_observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (999999,'As-of Fixture','NYK','asof-fixture','2026-09-28',2026,
                 True,'BOS',21,'nba','a'*64,'b'*64,observed))
            query="""SELECT payload,record_available_at FROM public.dashboard_gamelogs_asof
                WHERE sport='nba' AND player_id='999999' AND game_key='asof-fixture'
                  AND record_available_at<=%s"""
            assert conn.execute(query,(observed-timedelta(microseconds=1),)).fetchone() is None
            payload,available=conn.execute(query,(observed,)).fetchone()
            assert available==observed and payload['points']==21
            assert 'record_available_at' not in payload
            roles={r[0] for r in conn.execute(
                "SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)",
                (['anon','authenticated','sportsbet_worker','sportsbet_dashboard'],)).fetchall()}
            for role in ('anon','authenticated','sportsbet_worker'):
                if role in roles:
                    assert not conn.execute(
                        'SELECT has_table_privilege(%s,%s,%s)',
                        (role,'public.dashboard_gamelogs_asof','SELECT')).fetchone()[0]
            if 'sportsbet_dashboard' in roles:
                assert conn.execute(
                    'SELECT has_table_privilege(%s,%s,%s)',
                    ('sportsbet_dashboard','public.dashboard_gamelogs_asof','SELECT')).fetchone()[0]
        finally:
            conn.rollback()
