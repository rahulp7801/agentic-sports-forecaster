"""Retain CFB primary history across identical refreshes and later corrections."""
from alembic import op

revision = '0037_cfb_primary_revisions'
down_revision = '0036_dashboard_gamelogs_asof'
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE public.cfb_primary_revisions (
        revision_id BIGSERIAL PRIMARY KEY,
        athlete_id BIGINT NOT NULL CHECK (athlete_id > 0),
        game_id VARCHAR(20) NOT NULL,
        source_record_sha256 VARCHAR(64) NOT NULL
            CHECK (source_record_sha256 ~ '^[0-9a-f]{64}$'),
        source_observed_at TIMESTAMPTZ NOT NULL,
        replaced_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        row_data JSONB NOT NULL,
        CHECK (jsonb_typeof(row_data) = 'object'
            AND row_data->>'athlete_id' = athlete_id::text
            AND row_data->>'game_id' = game_id
            AND row_data->>'source_record_sha256' = source_record_sha256)
    )""")
    op.execute('CREATE INDEX idx_cfb_primary_revisions_asof ON '
        'public.cfb_primary_revisions (athlete_id,game_id,source_observed_at DESC)')
    op.execute('REVOKE ALL ON public.cfb_primary_revisions FROM PUBLIC')
    op.execute('REVOKE ALL ON SEQUENCE public.cfb_primary_revisions_revision_id_seq FROM PUBLIC')
    op.execute('ALTER TABLE public.cfb_primary_revisions ENABLE ROW LEVEL SECURITY')
    for role in ('anon','authenticated','sportsbet_dashboard'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            'REVOKE ALL ON public.cfb_primary_revisions FROM '+role+'; '
            'REVOKE ALL ON SEQUENCE public.cfb_primary_revisions_revision_id_seq FROM '+role+'; '
            'END IF; END $$')
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        GRANT SELECT,INSERT ON public.cfb_primary_revisions TO sportsbet_worker;
        GRANT USAGE,SELECT ON SEQUENCE public.cfb_primary_revisions_revision_id_seq TO sportsbet_worker;
        CREATE POLICY sportsbet_worker_read ON public.cfb_primary_revisions
            FOR SELECT TO sportsbet_worker USING (true);
        CREATE POLICY sportsbet_worker_insert ON public.cfb_primary_revisions
            FOR INSERT TO sportsbet_worker WITH CHECK (true);
    END IF; END $$""")
    op.execute("""CREATE FUNCTION public.archive_cfb_primary_revision() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        -- A release-wide hash or capture-time change does not make identical
        -- player statistics newly available. Preserve their first observation.
        IF to_jsonb(OLD) - ARRAY['source_sha256','source_player_sha256',
            'source_schedule_sha256','source_observed_at'] =
           to_jsonb(NEW) - ARRAY['source_sha256','source_player_sha256',
            'source_schedule_sha256','source_observed_at'] THEN
            RETURN NULL;
        END IF;
        INSERT INTO public.cfb_primary_revisions
            (athlete_id,game_id,source_record_sha256,source_observed_at,row_data)
        VALUES (OLD.athlete_id,OLD.game_id,OLD.source_record_sha256,
            OLD.source_observed_at,to_jsonb(OLD));
        -- A correction cannot be available before the database accepted it.
        NEW.source_observed_at := GREATEST(NEW.source_observed_at,
            OLD.source_observed_at + interval '1 microsecond',clock_timestamp());
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER archive_cfb_primary_revision
        BEFORE UPDATE ON public.cfb_player_gamelogs
        FOR EACH ROW EXECUTE FUNCTION public.archive_cfb_primary_revision()""")


def downgrade():
    op.execute('DROP TRIGGER archive_cfb_primary_revision ON public.cfb_player_gamelogs')
    op.execute('DROP FUNCTION public.archive_cfb_primary_revision()')
    op.execute('DROP TABLE public.cfb_primary_revisions')