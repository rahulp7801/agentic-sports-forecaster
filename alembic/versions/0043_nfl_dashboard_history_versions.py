"""Keep an earlier verified NFL supplement visible after a matching primary arrives."""
from alembic import op

revision = '0043_nfl_dashboard_versions'
down_revision = '0042_multisport_private_reports'
branch_labels = depends_on = None

# A matching primary replaces the supplement in the effective view. If the
# primary was first observed later, retain the supplement for older captures.
# A disagreement never enters this branch; the effective view still excludes it.
NFL_SUPPLEMENT_VERSION = """
    SELECT 'nfl'::text,g.game_date,
        COALESCE(p.player_name,
            s.manifest->'explicit_source'->'participation'->'row'->>'player_name')::varchar(100),
        g.game_id,
        jsonb_build_object('date',g.game_date,'player',
            COALESCE(p.player_name,
                s.manifest->'explicit_source'->'participation'->'row'->>'player_name'),
            'player_id',s.player_id,'team',s.stat_row->>'team',
            'opponent',CASE WHEN s.stat_row->>'team'=g.home_team
                THEN g.away_team ELSE g.home_team END,
            'is_home',s.stat_row->>'team'=g.home_team,
            'pass_yds',NULL::integer,'pass_tds',NULL::integer,
            'rush_yds',NULL::integer,
            'rec_yds',(s.stat_row->>'receiving_yards')::integer,
            'receptions',(s.stat_row->>'receptions')::integer),
        s.player_id,GREATEST(s.observed_at,s.inserted_at)
    FROM public.nfl_receiving_supplements s
    JOIN public.player_stats p
      ON p.player_id=s.player_id AND p.season=s.season AND p.week=s.week
     AND p.team IS NOT DISTINCT FROM s.stat_row->>'team'
     AND p.receiving_yards IS NOT DISTINCT FROM (s.stat_row->>'receiving_yards')::integer
     AND p.receptions IS NOT DISTINCT FROM (s.stat_row->>'receptions')::integer
    JOIN public.games g
      ON g.game_id=s.game_id AND g.season=s.season AND g.week=s.week
     AND g.game_date=(s.manifest->'game'->>'date')::date
     AND g.home_team=s.manifest->'explicit_source'->'participation'->>'home_team'
     AND g.away_team=s.manifest->'explicit_source'->'participation'->>'away_team'
    WHERE p.source_observed_at>GREATEST(s.observed_at,s.inserted_at)
      AND COALESCE(p.player_name,
          s.manifest->'explicit_source'->'participation'->'row'->>'player_name') IS NOT NULL
"""

def upgrade():
    op.execute('CREATE OR REPLACE VIEW public.dashboard_gamelog_versions '
        'WITH (security_barrier=true) AS '
        'SELECT sport,game_date,player_name,game_key,payload,player_id,record_available_at '
        'FROM public.dashboard_gamelogs_asof UNION ALL '
        + _cfb_original_version() + ' UNION ALL ' + NFL_SUPPLEMENT_VERSION)
    op.execute('REVOKE ALL ON public.dashboard_gamelog_versions FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_worker'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"
            +role+"') THEN REVOKE ALL ON public.dashboard_gamelog_versions FROM "
            +role+"; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') "
        "THEN GRANT SELECT ON public.dashboard_gamelog_versions TO sportsbet_dashboard; END IF; END $$")

def _cfb_original_version():
    return """
        SELECT 'cfb'::text,p.game_date,p.player_name,p.game_id,
            jsonb_build_object('date',p.game_date,'player',p.player_name,
                'player_id',p.athlete_id::text,'team',p.team_abbreviation,
                'opponent',p.opponent_abbreviation,'is_home',p.is_home,
                'pass_yds',p.passing_yards,'rush_yds',p.rushing_yards,
                'rec_yds',p.receiving_yards,'receptions',p.receptions),
            p.athlete_id::text,p.source_observed_at
        FROM public.cfb_player_gamelogs p
        JOIN public.cfb_receiving_supplements s
          ON s.athlete_id=p.athlete_id AND s.game_id=p.game_id
         AND s.primary_record_sha256=p.source_record_sha256
         AND p.source_provider='sportsdataverse_espn'
         AND to_jsonb(p) @> s.primary_row
    """

def downgrade():
    op.execute('CREATE OR REPLACE VIEW public.dashboard_gamelog_versions '
        'WITH (security_barrier=true) AS '
        'SELECT sport,game_date,player_name,game_key,payload,player_id,record_available_at '
        'FROM public.dashboard_gamelogs_asof UNION ALL ' + _cfb_original_version())
    op.execute('REVOKE ALL ON public.dashboard_gamelog_versions FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_worker'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"
            +role+"') THEN REVOKE ALL ON public.dashboard_gamelog_versions FROM "
            +role+"; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') "
        "THEN GRANT SELECT ON public.dashboard_gamelog_versions TO sportsbet_dashboard; END IF; END $$")
