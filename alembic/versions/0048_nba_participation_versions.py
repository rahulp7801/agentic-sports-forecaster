"""Append source-committed NBA minutes without changing frozen stat rows."""
from alembic import op

revision='0048_nba_participation_versions'
down_revision='0047_ngs_partition_versions'
branch_labels=depends_on=None


def upgrade():
    op.execute('''CREATE TABLE public.nba_participation_versions (
        version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        player_id INTEGER NOT NULL CHECK (player_id>0),
        player_name VARCHAR(100) NOT NULL CHECK (length(trim(player_name))>0),
        game_id VARCHAR(30) NOT NULL CHECK (game_id ~ '^[A-Za-z0-9_-]{1,30}$'),
        game_date DATE NOT NULL,season SMALLINT NOT NULL CHECK (season BETWEEN 2000 AND 2100),
        team_abbreviation VARCHAR(3) NOT NULL CHECK (team_abbreviation ~ '^[A-Z]{2,3}$'),
        minutes NUMERIC(4,1) CHECK (minutes BETWEEN 0 AND 999.9),
        source_provider VARCHAR(10) NOT NULL CHECK (source_provider IN ('nba','espn')),
        source_sha256 VARCHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
        source_record_sha256 VARCHAR(64) NOT NULL CHECK (source_record_sha256 ~ '^[0-9a-f]{64}$'),
        source_observed_at TIMESTAMPTZ NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        CHECK (game_date BETWEEN make_date(season,7,1) AND make_date(season+1,6,30)),
        CHECK (recorded_at>=source_observed_at))''')
    op.execute('CREATE INDEX idx_nba_participation_cutoff ON public.nba_participation_versions '
        '(player_id,game_id,recorded_at DESC,version_id DESC)')
    op.execute('''CREATE FUNCTION public.capture_nba_participation_version() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE previous public.nba_participation_versions%ROWTYPE;
        BEGIN
          PERFORM pg_advisory_xact_lock(20261009,hashtext(NEW.player_id::text||':'||NEW.game_id));
          SELECT * INTO previous FROM public.nba_participation_versions
            WHERE player_id=NEW.player_id AND game_id=NEW.game_id
            ORDER BY recorded_at DESC,version_id DESC LIMIT 1;
          IF previous.version_id IS NOT NULL AND previous.source_record_sha256=NEW.source_record_sha256
             AND previous.source_provider=NEW.source_provider
             AND (previous.player_name,previous.game_date,previous.season,previous.team_abbreviation,previous.minutes)
                 IS NOT DISTINCT FROM (NEW.player_name,NEW.game_date,NEW.season,NEW.team_abbreviation,NEW.minutes) THEN
            RETURN NULL;
          END IF;
          IF previous.version_id IS NOT NULL AND NEW.source_observed_at<previous.source_observed_at THEN
            RAISE EXCEPTION 'Older NBA participation cannot replace a newer observation';
          END IF;
          NEW.recorded_at:=GREATEST(clock_timestamp(),NEW.source_observed_at,
                                  previous.recorded_at+interval '1 microsecond');
          RETURN NEW;
        END $$''')
    op.execute('CREATE TRIGGER capture_nba_participation_version BEFORE INSERT ON '
        'public.nba_participation_versions FOR EACH ROW EXECUTE FUNCTION public.capture_nba_participation_version()')
    op.execute('ALTER TABLE public.nba_participation_versions ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON public.nba_participation_versions FROM PUBLIC')
    op.execute('REVOKE ALL ON SEQUENCE public.nba_participation_versions_version_id_seq FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION public.capture_nba_participation_version() FROM PUBLIC')
    op.execute('''DO $$ DECLARE role_name text; BEGIN
      FOREACH role_name IN ARRAY ARRAY['anon','authenticated','sportsbet_dashboard','sportsbet_worker'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
          EXECUTE format('REVOKE ALL ON public.nba_participation_versions FROM %I',role_name);
          EXECUTE format('REVOKE ALL ON SEQUENCE public.nba_participation_versions_version_id_seq FROM %I',role_name);
          EXECUTE format('REVOKE ALL ON FUNCTION public.capture_nba_participation_version() FROM %I',role_name);
        END IF;
      END LOOP;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        GRANT SELECT ON public.nba_participation_versions TO sportsbet_worker;
        GRANT INSERT (player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,
            source_provider,source_sha256,source_record_sha256,source_observed_at)
            ON public.nba_participation_versions TO sportsbet_worker;
        GRANT USAGE ON SEQUENCE public.nba_participation_versions_version_id_seq TO sportsbet_worker;
        CREATE POLICY sportsbet_worker_read ON public.nba_participation_versions
            FOR SELECT TO sportsbet_worker USING (true);
        CREATE POLICY sportsbet_worker_insert ON public.nba_participation_versions
            FOR INSERT TO sportsbet_worker WITH CHECK (true);
      END IF;
    END $$''')


def downgrade():
    op.execute('LOCK TABLE public.nba_participation_versions IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.nba_participation_versions) THEN
        RAISE EXCEPTION 'Retained NBA participation prevents downgrade; export and review first';
        END IF; END $$""")
    op.execute('DROP TABLE public.nba_participation_versions')
    op.execute('DROP FUNCTION public.capture_nba_participation_version()')
