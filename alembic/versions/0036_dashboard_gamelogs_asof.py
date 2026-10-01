"""Expose source-availability timing through a restricted game-log view."""
from alembic import op

revision = '0036_dashboard_gamelogs_asof'
down_revision = '0035_private_paper_receipts'
branch_labels = depends_on = None

QUERY = """
    SELECT 'nba'::text AS sport,n.game_date,n.player_name,n.game_id AS game_key,
        jsonb_build_object('date',n.game_date,'player',n.player_name,'player_id',n.player_id::text,
            'team',n.team_abbreviation,'opponent',n.opponent_team,'is_home',n.is_home,
            'points',n.points,'rebounds',n.rebounds,'assists',n.assists,
            'threes',n.threes_made,'steals',n.steals,'blocks',n.blocks,'minutes',n.minutes) AS payload,
        n.player_id::text AS player_id,n.source_observed_at AS record_available_at
    FROM public.nba_player_gamelogs n
    WHERE n.game_date IS NOT NULL AND n.player_name IS NOT NULL
    UNION ALL
    SELECT 'nfl',g.game_date,p.player_name,g.game_id,
        jsonb_build_object('date',g.game_date,'player',p.player_name,'player_id',p.player_id,
            'team',p.team,'opponent',CASE WHEN p.team=g.home_team THEN g.away_team ELSE g.home_team END,
            'is_home',p.team=g.home_team,'pass_yds',p.passing_yards,'pass_tds',p.passing_tds,
            'rush_yds',p.rushing_yards,'rec_yds',p.receiving_yards,'receptions',p.receptions),
        p.player_id::text,GREATEST(p.source_observed_at,p.supplement_inserted_at)
    FROM public.nfl_effective_receiving_gamelogs p
    JOIN LATERAL (
        SELECT MIN(game_date) AS game_date,MIN(game_id) AS game_id,
            MIN(home_team) AS home_team,MIN(away_team) AS away_team
        FROM public.games
        WHERE season=p.season AND week=p.week AND p.team IN (home_team,away_team)
        HAVING COUNT(*)=1
    ) g ON true
    WHERE p.player_name IS NOT NULL
    UNION ALL
    SELECT 'cfb',p.game_date,p.player_name,p.game_id,
        jsonb_build_object('date',p.game_date,'player',p.player_name,'player_id',p.athlete_id::text,
            'team',p.team_abbreviation,'opponent',p.opponent_abbreviation,'is_home',p.is_home,
            'pass_yds',p.passing_yards,'rush_yds',p.rushing_yards,
            'rec_yds',p.receiving_yards,'receptions',p.receptions),
        p.athlete_id::text,
        CASE WHEN p.history_policy_version='primary-v1' THEN p.source_observed_at
             WHEN p.history_policy_version='cfb-explicit-receiving-v1' THEN (
                 SELECT GREATEST(p.source_observed_at,s.inserted_at)
                 FROM public.cfb_receiving_supplements s
                 WHERE s.athlete_id=p.athlete_id AND s.game_id=p.game_id
                   AND s.effective_record_sha256=p.source_record_sha256
             )
             ELSE NULL::timestamptz END
    FROM public.cfb_effective_gamelogs p
"""

def upgrade():
    op.execute('CREATE VIEW public.dashboard_gamelogs_asof WITH (security_barrier=true) AS '+QUERY)
    op.execute('REVOKE ALL ON public.dashboard_gamelogs_asof FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_worker'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            "REVOKE ALL ON public.dashboard_gamelogs_asof FROM "+role+"; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') THEN "
        "GRANT SELECT ON public.dashboard_gamelogs_asof TO sportsbet_dashboard; END IF; END $$")

def downgrade():
    op.execute('DROP VIEW public.dashboard_gamelogs_asof')
