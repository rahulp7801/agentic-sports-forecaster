"""Expose source-timed primary NFL core stats to exact-player history cards."""
from alembic import op

revision = '0044_nfl_core_dashboard_history'
down_revision = '0043_nfl_dashboard_versions'
branch_labels = depends_on = None

VIEW = 'dashboard_nfl_core_gamelogs_asof'

QUERY = """
SELECT 'nfl'::text AS sport,g.game_date,p.player_name,g.game_id AS game_key,
    jsonb_build_object('date',g.game_date,'player',p.player_name,'player_id',p.player_id,
        'team',p.team,'opponent',CASE WHEN p.team=g.home_team THEN g.away_team ELSE g.home_team END,
        'is_home',p.team=g.home_team,'pass_yds',p.passing_yards,'pass_tds',p.passing_tds,
        'rush_yds',p.rushing_yards,'rec_yds',NULL::integer,'receptions',NULL::integer) AS payload,
    jsonb_build_object('player_id',p.player_id,'season',p.season,'week',p.week,
        'team',p.team,'passing_yards',p.passing_yards,'rushing_yards',p.rushing_yards,
        'receiving_yards',p.receiving_yards,'receptions',p.receptions,
        'source_record_sha256',p.source_record_sha256) AS source_row,
    p.player_id::text AS player_id,p.source_observed_at AS record_available_at
FROM public.player_stats p
JOIN LATERAL (
    SELECT MIN(game_date) AS game_date,MIN(game_id) AS game_id,
        MIN(home_team) AS home_team,MIN(away_team) AS away_team
    FROM public.games
    WHERE season=p.season AND week=p.week AND p.team IN (home_team,away_team)
    HAVING COUNT(*)=1
) g ON true
WHERE p.player_name IS NOT NULL AND p.source_provider='nflverse'
  AND p.source_sha256 ~ '^[0-9a-f]{64}$'
  AND p.source_record_sha256 ~ '^[0-9a-f]{64}$'
  AND p.source_observed_at IS NOT NULL
"""


def upgrade():
    op.execute('CREATE VIEW public.'+VIEW+' WITH (security_barrier=true) AS '+QUERY)
    op.execute('REVOKE ALL ON public.'+VIEW+' FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_worker'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"
            +role+"') THEN REVOKE ALL ON public."+VIEW+" FROM "+role+"; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') "
        "THEN GRANT SELECT ON public."+VIEW+" TO sportsbet_dashboard; END IF; END $$")


def downgrade():
    op.execute('DROP VIEW public.'+VIEW)
