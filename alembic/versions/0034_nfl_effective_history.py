"""Use exact archived NFL receiving games through a restricted effective view."""
from alembic import op

revision = '0034_nfl_effective_history'
down_revision = '0033_nfl_history_supplements'
branch_labels = depends_on = None
VIEW = 'nfl_effective_receiving_gamelogs'

QUERY = """WITH conflicts AS (
    SELECT s.player_id FROM public.nfl_receiving_supplements s
    JOIN public.player_stats p USING(player_id,season,week)
    WHERE p.team IS DISTINCT FROM s.stat_row->>'team'
       OR p.receiving_yards IS DISTINCT FROM (s.stat_row->>'receiving_yards')::integer
       OR p.receptions IS DISTINCT FROM (s.stat_row->>'receptions')::integer
)
SELECT p.player_id,p.season,p.week,p.player_name,p.team,p.opponent_team,p.home_away,
    p.passing_yards,p.passing_tds,p.rushing_yards,p.receiving_yards,p.receptions,
    p.source_provider,p.source_sha256,p.source_record_sha256,p.source_observed_at,
    NULL::timestamptz AS supplement_inserted_at,NULL::jsonb AS supplement_manifest
FROM public.player_stats p
WHERE NOT EXISTS (SELECT 1 FROM conflicts c WHERE c.player_id=p.player_id)
UNION ALL
SELECT s.player_id,s.season,s.week,
    COALESCE((SELECT p.player_name FROM public.player_stats p WHERE p.player_id=s.player_id
        AND p.player_name IS NOT NULL ORDER BY p.season DESC,p.week DESC LIMIT 1),
        s.manifest->'explicit_source'->'participation'->'row'->>'player_name'),
    s.stat_row->>'team',
    CASE WHEN s.stat_row->>'team'=g.home_team THEN g.away_team ELSE g.home_team END,
    CASE WHEN s.stat_row->>'team'=g.home_team THEN 'home' ELSE 'away' END,
    NULL::integer,NULL::integer,NULL::integer,
    (s.stat_row->>'receiving_yards')::integer,(s.stat_row->>'receptions')::integer,
    'nflverse_espn_supplement',s.source_sha256,s.stat_record_sha256,s.observed_at,
    s.inserted_at,s.manifest
FROM public.nfl_receiving_supplements s
JOIN public.games g ON g.game_id=s.game_id AND g.season=s.season AND g.week=s.week
    AND g.game_date=(s.manifest->'game'->>'date')::date
    AND g.home_team=s.manifest->'explicit_source'->'participation'->>'home_team'
    AND g.away_team=s.manifest->'explicit_source'->'participation'->>'away_team'
WHERE NOT EXISTS (SELECT 1 FROM public.player_stats p
    WHERE p.player_id=s.player_id AND p.season=s.season AND p.week=s.week)
  AND NOT EXISTS (SELECT 1 FROM conflicts c WHERE c.player_id=s.player_id)
"""

OLD_DASHBOARD = "\n    SELECT 'nba'::text AS sport, game_date, player_name, game_id AS game_key,\n        jsonb_build_object('date',game_date,'player',player_name,'player_id',player_id::text,\n            'team',team_abbreviation,'opponent',opponent_team,'is_home',is_home,\n            'points',points,'rebounds',rebounds,'assists',assists,'threes',threes_made,\n            'steals',steals,'blocks',blocks,'minutes',minutes) AS payload, player_id::text AS player_id\n    FROM public.nba_player_gamelogs\n    WHERE game_date IS NOT NULL AND player_name IS NOT NULL\n    UNION ALL\n    SELECT 'nfl',g.game_date,p.player_name,g.game_id,\n        jsonb_build_object('date',g.game_date,'player',p.player_name,'player_id',p.player_id,'team',p.team,\n            'opponent',CASE WHEN p.team=g.home_team THEN g.away_team ELSE g.home_team END,\n            'is_home',p.team=g.home_team,'pass_yds',p.passing_yards,'pass_tds',p.passing_tds,\n            'rush_yds',p.rushing_yards,'rec_yds',p.receiving_yards,'receptions',p.receptions),p.player_id::text\n    FROM public.player_stats p\n    JOIN LATERAL (\n        SELECT MIN(game_date) AS game_date,MIN(game_id) AS game_id,\n            MIN(home_team) AS home_team,MIN(away_team) AS away_team\n        FROM public.games\n        WHERE season=p.season AND week=p.week AND p.team IN (home_team,away_team)\n        HAVING COUNT(*)=1\n    ) g ON true\n    WHERE p.player_name IS NOT NULL\n\n    UNION ALL\n    SELECT 'cfb',game_date,player_name,game_id,\n        jsonb_build_object('date',game_date,'player',player_name,'player_id',athlete_id::text,\n            'team',team_abbreviation,'opponent',opponent_abbreviation,'is_home',is_home,\n            'pass_yds',passing_yards,'rush_yds',rushing_yards,\n            'rec_yds',receiving_yards,'receptions',receptions),athlete_id::text\n    FROM public.cfb_effective_gamelogs\n"
NEW_DASHBOARD = OLD_DASHBOARD.replace("FROM public.player_stats p", "FROM public.nfl_effective_receiving_gamelogs p")


def upgrade():
    op.execute('CREATE VIEW public.'+VIEW+' WITH (security_barrier=true) AS '+QUERY)
    for role in ('PUBLIC','anon','authenticated','sportsbet_dashboard'):
        if role=='PUBLIC':
            op.execute('REVOKE ALL ON public.'+VIEW+' FROM PUBLIC')
        else:
            op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
                'REVOKE ALL ON public.'+VIEW+' FROM '+role+'; END IF; END $$')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN "
        'GRANT SELECT ON public.'+VIEW+' TO sportsbet_worker; END IF; END $$')
    op.execute('CREATE OR REPLACE VIEW public.dashboard_gamelogs WITH (security_barrier=true) AS '+NEW_DASHBOARD)


def downgrade():
    op.execute('CREATE OR REPLACE VIEW public.dashboard_gamelogs WITH (security_barrier=true) AS '+OLD_DASHBOARD)
    op.execute('DROP VIEW public.'+VIEW)
