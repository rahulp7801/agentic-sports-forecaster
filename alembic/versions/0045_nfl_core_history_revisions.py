"""Preserve forward NFL core-card evidence without changing live model rows."""
from alembic import op

revision = '0045_nfl_core_history_revisions'
down_revision = '0044_nfl_core_dashboard_history'
branch_labels = depends_on = None

QUERY = """
WITH primary_versions AS (
    SELECT p.*,GREATEST(p.source_observed_at,(SELECT MAX(r.replaced_at)
        FROM public.nfl_primary_revisions r
        WHERE (r.player_id,r.season,r.week)=(p.player_id,p.season,p.week))) AS history_available_at
    FROM public.player_stats p
    UNION ALL
    SELECT p.*,r.record_available_at AS history_available_at
    FROM public.nfl_primary_revisions r
    CROSS JOIN LATERAL jsonb_populate_record(NULL::public.player_stats,r.row_data) p
)

SELECT 'nfl'::text AS sport,g.game_date,p.player_name,g.game_id AS game_key,
    jsonb_build_object('date',g.game_date,'player',p.player_name,'player_id',p.player_id,
        'team',p.team,'opponent',CASE WHEN p.team=g.home_team THEN g.away_team ELSE g.home_team END,
        'is_home',p.team=g.home_team,'pass_yds',p.passing_yards,'pass_tds',p.passing_tds,
        'rush_yds',p.rushing_yards,'rec_yds',NULL::integer,'receptions',NULL::integer) AS payload,
    jsonb_build_object('player_id',p.player_id,'season',p.season,'week',p.week,
        'team',p.team,'passing_yards',p.passing_yards,'rushing_yards',p.rushing_yards,
        'receiving_yards',p.receiving_yards,'receptions',p.receptions,
        'source_record_sha256',p.source_record_sha256) AS source_row,
    p.player_id::text AS player_id,p.history_available_at AS record_available_at
FROM primary_versions p
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

PREVIOUS_QUERY = """

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
    op.execute("""CREATE TABLE public.nfl_primary_revisions (
        revision_id BIGSERIAL PRIMARY KEY,
        player_id VARCHAR(20) NOT NULL,
        season SMALLINT NOT NULL,
        week SMALLINT NOT NULL,
        source_record_sha256 VARCHAR(64) NOT NULL
            CHECK (source_record_sha256 ~ '^[0-9a-f]{64}$'),
        source_observed_at TIMESTAMPTZ NOT NULL,
        record_available_at TIMESTAMPTZ NOT NULL,
        replaced_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        row_data JSONB NOT NULL,
        CHECK (record_available_at >= source_observed_at),
        CHECK (jsonb_typeof(row_data)='object'
            AND row_data->>'player_id'=player_id
            AND (row_data->>'season')::integer=season
            AND (row_data->>'week')::integer=week
            AND row_data->>'source_record_sha256'=source_record_sha256)
    )""")
    op.execute('CREATE INDEX idx_nfl_primary_revisions_asof ON '
        'public.nfl_primary_revisions (player_id,season,week,record_available_at DESC)')
    op.execute('ALTER TABLE public.nfl_primary_revisions ENABLE ROW LEVEL SECURITY')
    # Only the owner-executed trigger writes archives. No application role can
    # insert a fabricated historical version or edit/delete a saved version.
    op.execute('REVOKE ALL ON public.nfl_primary_revisions FROM PUBLIC')
    op.execute('REVOKE ALL ON SEQUENCE public.nfl_primary_revisions_revision_id_seq FROM PUBLIC')
    op.execute("""DO $$ DECLARE role_name TEXT;
    BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','sportsbet_dashboard','sportsbet_worker'] LOOP
            IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=role_name) THEN
                EXECUTE format('REVOKE ALL ON public.nfl_primary_revisions FROM %I',role_name);
                EXECUTE format('REVOKE ALL ON SEQUENCE public.nfl_primary_revisions_revision_id_seq FROM %I',role_name);
            END IF;
        END LOOP;
    END $$""")
    op.execute("""CREATE FUNCTION public.archive_nfl_primary_revision() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE available timestamptz; moment timestamptz;
    BEGIN
        -- Ignore bundle-only refreshes and derived schedule enrichment.
        -- The existing ingester still owns observation preservation on refresh.
        IF to_jsonb(OLD) - ARRAY['source_sha256','source_observed_at','opponent_team','home_away'] =
           to_jsonb(NEW) - ARRAY['source_sha256','source_observed_at','opponent_team','home_away'] THEN
            RETURN NEW;
        END IF;
        -- Legacy/unproven rows are not manufactured into source-backed history.
        IF OLD.source_provider='nflverse'
           AND OLD.source_sha256 ~ '^[0-9a-f]{64}$'
           AND OLD.source_record_sha256 ~ '^[0-9a-f]{64}$'
           AND OLD.source_observed_at IS NOT NULL THEN
            available:=GREATEST(OLD.source_observed_at,
                (SELECT MAX(r.replaced_at) FROM public.nfl_primary_revisions r
                 WHERE (r.player_id,r.season,r.week)=(OLD.player_id,OLD.season,OLD.week)));
            -- Host and database clocks can differ. The transition cannot
            -- precede either source receipt or the previous retained version.
            moment:=GREATEST(clock_timestamp(),NEW.source_observed_at,
                             available+interval '1 microsecond');
            INSERT INTO public.nfl_primary_revisions
                (player_id,season,week,source_record_sha256,source_observed_at,
                 record_available_at,replaced_at,row_data)
            VALUES (OLD.player_id,OLD.season,OLD.week,OLD.source_record_sha256,
                OLD.source_observed_at,available,moment,to_jsonb(OLD));
        END IF;
        -- No forecast/model timestamp or stat is changed by this trigger.
        RETURN NEW;
    END $$""")
    op.execute('REVOKE ALL ON FUNCTION public.archive_nfl_primary_revision() FROM PUBLIC')
    op.execute("""DO $$ DECLARE role_name TEXT;
    BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','sportsbet_dashboard','sportsbet_worker'] LOOP
            IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=role_name) THEN
                EXECUTE format('REVOKE ALL ON FUNCTION public.archive_nfl_primary_revision() FROM %I',role_name);
            END IF;
        END LOOP;
    END $$""")
    op.execute("""CREATE TRIGGER archive_nfl_primary_revision
        BEFORE UPDATE ON public.player_stats FOR EACH ROW
        EXECUTE FUNCTION public.archive_nfl_primary_revision()""")
    op.execute('CREATE OR REPLACE VIEW public.dashboard_nfl_core_gamelogs_asof '
        'WITH (security_barrier=true) AS '+QUERY)


def downgrade():
    # Block corrections before checking so an in-flight worker cannot add an
    # archive between the evidence guard and destructive DDL.
    op.execute('LOCK TABLE public.player_stats,public.nfl_primary_revisions IN ACCESS EXCLUSIVE MODE')
    # A populated archive is evidence, not disposable migration scratch data.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.nfl_primary_revisions) THEN
        RAISE EXCEPTION 'Retained NFL evidence prevents downgrade; export and review first';
        END IF; END $$""")
    op.execute('CREATE OR REPLACE VIEW public.dashboard_nfl_core_gamelogs_asof '
        'WITH (security_barrier=true) AS '+PREVIOUS_QUERY)
    op.execute('DROP TRIGGER archive_nfl_primary_revision ON public.player_stats')
    op.execute('DROP FUNCTION public.archive_nfl_primary_revision()')
    op.execute('DROP TABLE public.nfl_primary_revisions')
