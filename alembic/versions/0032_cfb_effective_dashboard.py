"""Expose verified CFB history through the restricted public projection."""
from alembic import op

revision = "0032_cfb_effective_dashboard"
down_revision = "0031_cfb_history_supplements"
branch_labels = depends_on = None

OLD_VIEW = "\n    SELECT 'nba'::text AS sport, game_date, player_name, game_id AS game_key,\n        jsonb_build_object('date',game_date,'player',player_name,'player_id',player_id::text,\n            'team',team_abbreviation,'opponent',opponent_team,'is_home',is_home,\n            'points',points,'rebounds',rebounds,'assists',assists,'threes',threes_made,\n            'steals',steals,'blocks',blocks,'minutes',minutes) AS payload, player_id::text AS player_id\n    FROM public.nba_player_gamelogs\n    WHERE game_date IS NOT NULL AND player_name IS NOT NULL\n    UNION ALL\n    SELECT 'nfl',g.game_date,p.player_name,g.game_id,\n        jsonb_build_object('date',g.game_date,'player',p.player_name,'player_id',p.player_id,'team',p.team,\n            'opponent',CASE WHEN p.team=g.home_team THEN g.away_team ELSE g.home_team END,\n            'is_home',p.team=g.home_team,'pass_yds',p.passing_yards,'pass_tds',p.passing_tds,\n            'rush_yds',p.rushing_yards,'rec_yds',p.receiving_yards,'receptions',p.receptions),p.player_id::text\n    FROM public.player_stats p\n    JOIN LATERAL (\n        SELECT MIN(game_date) AS game_date,MIN(game_id) AS game_id,\n            MIN(home_team) AS home_team,MIN(away_team) AS away_team\n        FROM public.games\n        WHERE season=p.season AND week=p.week AND p.team IN (home_team,away_team)\n        HAVING COUNT(*)=1\n    ) g ON true\n    WHERE p.player_name IS NOT NULL\n\n    UNION ALL\n    SELECT 'cfb',game_date,player_name,game_id,\n        jsonb_build_object('date',game_date,'player',player_name,'player_id',athlete_id::text,\n            'team',team_abbreviation,'opponent',opponent_abbreviation,'is_home',is_home,\n            'pass_yds',passing_yards,'rush_yds',rushing_yards,\n            'rec_yds',receiving_yards,'receptions',receptions),athlete_id::text\n    FROM public.cfb_player_gamelogs\n"
NEW_VIEW = OLD_VIEW.replace("FROM public.cfb_player_gamelogs", "FROM public.cfb_effective_gamelogs")

def replace_view(query):
    op.execute('CREATE OR REPLACE VIEW public.dashboard_gamelogs WITH (security_barrier=true) AS '+query)
    op.execute('REVOKE ALL ON public.dashboard_gamelogs FROM PUBLIC')
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON public.dashboard_gamelogs FROM anon;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON public.dashboard_gamelogs FROM authenticated;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') THEN
        GRANT SELECT ON public.dashboard_gamelogs TO sportsbet_dashboard;
      END IF;
    END $$""")

def upgrade():
    replace_view(NEW_VIEW)

def downgrade():
    replace_view(OLD_VIEW)
