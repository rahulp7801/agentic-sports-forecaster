"""Keep a verified CFB row's earlier unknown stats visible before its supplement."""
from alembic import op

revision = '0041_cfb_dashboard_versions'
down_revision = '0040_private_priced_edge_reports'
branch_labels = depends_on = None


def upgrade():
    # The base view exposes only the latest effective receiving row. Retain the
    # original source version solely when the matching supplement is still valid.
    # The API chooses the latest version available at the requested capture time.
    op.execute("""CREATE VIEW public.dashboard_gamelog_versions WITH (security_barrier=true) AS
        SELECT sport,game_date,player_name,game_key,payload,player_id,record_available_at
        FROM public.dashboard_gamelogs_asof
        UNION ALL
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
         AND to_jsonb(p) @> s.primary_row""")
    op.execute('REVOKE ALL ON public.dashboard_gamelog_versions FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_worker'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            "REVOKE ALL ON public.dashboard_gamelog_versions FROM "+role+"; END IF; END $$")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_dashboard') THEN "
        "GRANT SELECT ON public.dashboard_gamelog_versions TO sportsbet_dashboard; END IF; END $$")


def downgrade():
    op.execute('DROP VIEW public.dashboard_gamelog_versions')
