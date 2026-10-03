"""Preserve complete private tracking versions and narrow worker replacements."""
from alembic import op

revision = '0047_ngs_partition_versions'
down_revision = '0046_private_waitlist'
branch_labels = depends_on = None

FUNCTION = 'public.replace_ngs_partition(integer,text,text,timestamp with time zone,jsonb)'


def upgrade():
    op.execute('LOCK TABLE public.ngs_stats IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.ngs_stats GROUP BY season,stat_type
                 HAVING count(DISTINCT source_sha256)<>1) THEN
        RAISE EXCEPTION 'Mixed tracking partitions require review before versioning';
      END IF;
    END $$""")
    op.execute("""CREATE TABLE public.ngs_partition_versions (
        version_id BIGSERIAL PRIMARY KEY,
        season SMALLINT NOT NULL CHECK (season BETWEEN 2016 AND 2100),
        stat_type VARCHAR(10) NOT NULL CHECK (stat_type IN ('passing','receiving','rushing')),
        source_sha256 VARCHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
        record_set_sha256 VARCHAR(64) NOT NULL CHECK (record_set_sha256 ~ '^[0-9a-f]{64}$'),
        source_observed_at TIMESTAMPTZ NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        normalization_version TEXT NOT NULL
            CHECK (normalization_version IN ('legacy-ngs-row-v1','ngs-db-precision-v2')),
        row_count INTEGER NOT NULL CHECK (row_count BETWEEN 1 AND 10000),
        CHECK (recorded_at>=source_observed_at))""")
    op.execute('CREATE INDEX idx_ngs_partition_cutoff ON public.ngs_partition_versions '
               '(season,stat_type,recorded_at DESC,version_id DESC)')
    op.execute('ALTER TABLE public.ngs_stats ADD COLUMN partition_version_id BIGINT '
               'REFERENCES public.ngs_partition_versions(version_id)')
    op.execute("""INSERT INTO public.ngs_partition_versions
        (season,stat_type,source_sha256,record_set_sha256,source_observed_at,
         recorded_at,normalization_version,row_count)
        SELECT season,stat_type,min(source_sha256),
          encode(sha256(convert_to(string_agg(source_record_sha256,E'\\n'
                    ORDER BY source_record_sha256),'UTF8')),'hex'),
          max(source_observed_at),max(source_observed_at),'legacy-ngs-row-v1',count(*)
        FROM public.ngs_stats GROUP BY season,stat_type""")
    op.execute('UPDATE public.ngs_stats n SET partition_version_id=v.version_id '
               'FROM public.ngs_partition_versions v WHERE (n.season,n.stat_type)=(v.season,v.stat_type)')
    op.execute('ALTER TABLE public.ngs_stats ALTER COLUMN partition_version_id SET NOT NULL')
    op.execute("""CREATE TABLE public.ngs_partition_rows (
        version_id BIGINT NOT NULL REFERENCES public.ngs_partition_versions(version_id),
        player_gsis_id VARCHAR(20) NOT NULL, week SMALLINT NOT NULL,
        row_data JSONB NOT NULL,
        PRIMARY KEY(version_id,player_gsis_id,week),
        CHECK (jsonb_typeof(row_data)='object'
            AND row_data->>'player_gsis_id'=player_gsis_id
            AND (row_data->>'week')::integer=week
            AND (row_data->>'partition_version_id')::bigint=version_id))""")
    op.execute('CREATE VIEW public.ngs_partition_catalog WITH (security_barrier=true) '
               'AS SELECT * FROM public.ngs_partition_versions')
    op.execute("""CREATE VIEW public.ngs_history_versions WITH (security_barrier=true) AS
        SELECT n.*,v.recorded_at AS partition_available_at,v.record_set_sha256,
            v.normalization_version,v.row_count AS partition_rows
        FROM public.ngs_stats n JOIN public.ngs_partition_versions v
            ON n.partition_version_id=v.version_id
        UNION ALL
        SELECT n.*,v.recorded_at,v.record_set_sha256,v.normalization_version,v.row_count
        FROM public.ngs_partition_rows h
        CROSS JOIN LATERAL jsonb_populate_record(NULL::public.ngs_stats,h.row_data) n
        JOIN public.ngs_partition_versions v ON h.version_id=v.version_id""")
    op.execute("""CREATE FUNCTION public.replace_ngs_partition(target_season integer,
        target_type text,source_hash text,observed_at timestamptz,payload jsonb)
        RETURNS TABLE(version_id bigint,unchanged boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $function$
        DECLARE existing public.ngs_partition_versions%ROWTYPE;
            total integer; digest text; moment timestamptz; next_id bigint;
            expected_url text;
        BEGIN
          IF target_season IS NULL OR target_season NOT BETWEEN 2016 AND 2100
            OR target_type IS NULL OR target_type NOT IN ('passing','receiving','rushing')
            OR source_hash IS NULL OR source_hash !~ '^[0-9a-f]{64}$'
            OR observed_at IS NULL OR observed_at>clock_timestamp()
            OR payload IS NULL OR jsonb_typeof(payload)<>'array'
            OR jsonb_array_length(payload) NOT BETWEEN 1 AND 10000
            OR pg_column_size(payload)>10000000 THEN
            RAISE EXCEPTION 'Invalid tracking partition input';
          END IF;
          IF EXISTS (SELECT 1 FROM jsonb_array_elements(payload) r
                     WHERE jsonb_typeof(r)<>'object') THEN
            RAISE EXCEPTION 'Invalid tracking row input';
          END IF;
          IF EXISTS (SELECT 1 FROM jsonb_array_elements(payload) r,
                     LATERAL jsonb_object_keys(r) k WHERE k<>ALL(ARRAY[
                       'player_gsis_id','season','week','stat_type','team_abbr','player_position',
                       'avg_time_to_throw','avg_completed_air_yards','avg_intended_air_yards',
                       'aggressiveness','passer_rating','attempts','avg_separation','avg_cushion',
                       'avg_yac','avg_yac_above_expectation','catch_percentage','targets','receptions',
                       'efficiency','percent_attempts_gte_eight_defenders','rush_yards_over_expected',
                       'avg_time_to_los','rush_attempts','source_provider','source_url','source_sha256',
                       'source_record_sha256','source_observed_at'])) THEN
            RAISE EXCEPTION 'Unknown tracking row fields';
          END IF;
          expected_url:='https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_'||target_type||'.parquet';
          IF EXISTS (SELECT 1 FROM jsonb_populate_recordset(NULL::public.ngs_stats,payload) n
             WHERE n.season IS DISTINCT FROM target_season OR n.stat_type IS DISTINCT FROM target_type
               OR n.source_provider IS DISTINCT FROM 'nflverse_ngs'
               OR n.source_sha256 IS DISTINCT FROM source_hash
               OR n.source_url IS DISTINCT FROM expected_url
               OR n.source_observed_at IS DISTINCT FROM observed_at
               OR n.source_record_sha256 IS NULL OR n.source_record_sha256 !~ '^[0-9a-f]{64}$'
               OR n.id IS NOT NULL OR n.partition_version_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM jsonb_populate_recordset(NULL::public.ngs_stats,payload) n
                        GROUP BY n.player_gsis_id,n.week HAVING count(*)<>1) THEN
            RAISE EXCEPTION 'Contradictory tracking partition input';
          END IF;
          SELECT count(*),encode(sha256(convert_to(string_agg(n.source_record_sha256,E'\\n'
                 ORDER BY n.source_record_sha256),'UTF8')),'hex') INTO total,digest
            FROM jsonb_populate_recordset(NULL::public.ngs_stats,payload) n;
          PERFORM pg_advisory_xact_lock(20261008,hashtext(target_season::text||':'||target_type));
          SELECT v.* INTO existing FROM public.ngs_partition_versions v
            WHERE v.season=target_season AND v.stat_type=target_type
            ORDER BY v.recorded_at DESC,v.version_id DESC LIMIT 1;
          IF existing.version_id IS NOT NULL AND existing.source_sha256=source_hash
             AND existing.record_set_sha256=digest AND existing.row_count=total
             AND (SELECT jsonb_agg(to_jsonb(n)-ARRAY['id','partition_version_id','source_observed_at']
                    ORDER BY n.player_gsis_id,n.week) FROM public.ngs_stats n
                    WHERE n.season=target_season AND n.stat_type=target_type)=
                 (SELECT jsonb_agg(to_jsonb(n)-ARRAY['id','partition_version_id','source_observed_at']
                    ORDER BY n.player_gsis_id,n.week)
                    FROM jsonb_populate_recordset(NULL::public.ngs_stats,payload) n) THEN
            RETURN QUERY SELECT existing.version_id,true; RETURN;
          END IF;
          IF existing.version_id IS NOT NULL AND observed_at<existing.source_observed_at THEN
            RAISE EXCEPTION 'Older tracking source cannot replace a newer partition';
          END IF;
          INSERT INTO public.ngs_partition_rows(version_id,player_gsis_id,week,row_data)
             SELECT n.partition_version_id,n.player_gsis_id,n.week,to_jsonb(n)
             FROM public.ngs_stats n WHERE n.season=target_season AND n.stat_type=target_type;
          moment:=GREATEST(clock_timestamp(),observed_at,existing.recorded_at+interval '1 microsecond');
          INSERT INTO public.ngs_partition_versions(season,stat_type,source_sha256,
              record_set_sha256,source_observed_at,recorded_at,normalization_version,row_count)
             VALUES(target_season,target_type,source_hash,digest,observed_at,moment,
                    'ngs-db-precision-v2',total) RETURNING ngs_partition_versions.version_id INTO next_id;
          DELETE FROM public.ngs_stats n WHERE n.season=target_season AND n.stat_type=target_type;
          INSERT INTO public.ngs_stats (
              player_gsis_id,season,week,stat_type,team_abbr,player_position,
              avg_time_to_throw,avg_completed_air_yards,avg_intended_air_yards,
              aggressiveness,passer_rating,attempts,avg_separation,avg_cushion,
              avg_yac,avg_yac_above_expectation,catch_percentage,targets,receptions,
              efficiency,percent_attempts_gte_eight_defenders,rush_yards_over_expected,
              avg_time_to_los,rush_attempts,source_provider,source_url,source_sha256,
              source_record_sha256,source_observed_at,partition_version_id)
             SELECT n.player_gsis_id,n.season,n.week,n.stat_type,n.team_abbr,n.player_position,
              n.avg_time_to_throw,n.avg_completed_air_yards,n.avg_intended_air_yards,
              n.aggressiveness,n.passer_rating,n.attempts,n.avg_separation,n.avg_cushion,
              n.avg_yac,n.avg_yac_above_expectation,n.catch_percentage,n.targets,n.receptions,
              n.efficiency,n.percent_attempts_gte_eight_defenders,n.rush_yards_over_expected,
              n.avg_time_to_los,n.rush_attempts,n.source_provider,n.source_url,n.source_sha256,
              n.source_record_sha256,n.source_observed_at,next_id
             FROM jsonb_populate_recordset(NULL::public.ngs_stats,payload) n;
          RETURN QUERY SELECT next_id,false;
        END $function$""")
    for table in ('ngs_partition_versions','ngs_partition_rows'):
        op.execute('ALTER TABLE public.'+table+' ENABLE ROW LEVEL SECURITY')
    targets='public.ngs_partition_versions,public.ngs_partition_rows,public.ngs_partition_catalog,public.ngs_history_versions'
    op.execute('REVOKE ALL ON '+targets+' FROM PUBLIC')
    op.execute('REVOKE ALL ON SEQUENCE public.ngs_partition_versions_version_id_seq FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION '+FUNCTION+' FROM PUBLIC')
    op.execute("""DO $$ DECLARE role_name text; BEGIN
      FOREACH role_name IN ARRAY ARRAY['anon','authenticated','sportsbet_dashboard','sportsbet_worker'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
          EXECUTE format('REVOKE ALL ON public.ngs_partition_versions,public.ngs_partition_rows,public.ngs_partition_catalog,public.ngs_history_versions FROM %I',role_name);
          EXECUTE format('REVOKE ALL ON SEQUENCE public.ngs_partition_versions_version_id_seq FROM %I',role_name);
          EXECUTE format('REVOKE ALL ON FUNCTION public.replace_ngs_partition(integer,text,text,timestamp with time zone,jsonb) FROM %I',role_name);
        END IF;
      END LOOP;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        GRANT SELECT ON public.ngs_partition_catalog,public.ngs_history_versions TO sportsbet_worker;
        GRANT EXECUTE ON FUNCTION public.replace_ngs_partition(integer,text,text,timestamp with time zone,jsonb) TO sportsbet_worker;
        REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON public.ngs_stats FROM sportsbet_worker;
      END IF;
    END $$""")


def downgrade():
    op.execute('LOCK TABLE public.ngs_stats,public.ngs_partition_versions,public.ngs_partition_rows IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.ngs_partition_rows)
        OR EXISTS (SELECT 1 FROM public.ngs_partition_versions WHERE normalization_version<>'legacy-ngs-row-v1') THEN
        RAISE EXCEPTION 'Retained tracking versions prevent downgrade; export and review first';
      END IF;
    END $$""")
    op.execute('DROP FUNCTION '+FUNCTION)
    op.execute('DROP VIEW public.ngs_history_versions')
    op.execute('DROP VIEW public.ngs_partition_catalog')
    op.execute('DROP TABLE public.ngs_partition_rows')
    op.execute('ALTER TABLE public.ngs_stats DROP COLUMN partition_version_id')
    op.execute('DROP TABLE public.ngs_partition_versions')
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        GRANT INSERT,UPDATE,DELETE ON public.ngs_stats TO sportsbet_worker;
    END IF; END $$""")
