"""Stage append-only NFL receiving evidence without changing model readers."""
from alembic import op

revision = '0033_nfl_history_supplements'
down_revision = '0032_cfb_effective_dashboard'
branch_labels = depends_on = None
TABLES = ('nfl_history_source_bundles', 'nfl_receiving_supplements')


def upgrade():
    op.execute("""CREATE TABLE public.nfl_history_source_bundles (
        bundle_sha256 varchar(64) PRIMARY KEY,
        response_text text NOT NULL,
        archived_at timestamptz NOT NULL DEFAULT now(),
        CHECK (octet_length(response_text) BETWEEN 1 AND 25000000
            AND jsonb_typeof(response_text::jsonb)='object'
            AND bundle_sha256=encode(sha256(convert_to(response_text,'UTF8')),'hex'))
    )""")
    op.execute("""CREATE TABLE public.nfl_receiving_supplements (
        player_id varchar(10) NOT NULL CHECK (player_id ~ '^00-[0-9]{7}$'),
        season integer NOT NULL CHECK (season BETWEEN 2000 AND 2200),
        week integer NOT NULL CHECK (week BETWEEN 1 AND 18),
        game_id text NOT NULL REFERENCES public.games(game_id),
        bundle_sha256 varchar(64) NOT NULL REFERENCES public.nfl_history_source_bundles(bundle_sha256),
        stat_row jsonb NOT NULL,
        stat_record_sha256 varchar(64) NOT NULL CHECK (stat_record_sha256 ~ '^[0-9a-f]{64}$'),
        source_sha256 varchar(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
        manifest jsonb NOT NULL,
        observed_at timestamptz NOT NULL,
        inserted_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(player_id,season,week),
        CHECK (COALESCE(jsonb_typeof(stat_row)='object'
            AND stat_row ?& ARRAY['player_id','season','week','team','passing_yards','rushing_yards','receiving_yards','receptions']
            AND stat_row-'player_id'-'season'-'week'-'team'-'passing_yards'-'rushing_yards'-'receiving_yards'-'receptions'='{}'::jsonb
            AND stat_row->'player_id'=to_jsonb(player_id)
            AND stat_row->'season'=to_jsonb(season) AND stat_row->'week'=to_jsonb(week)
            AND stat_row->>'team' ~ '^[A-Z]{2,3}$'
            AND game_id ~ ('^' || season::text || '_' || lpad(week::text,2,'0') || '_[A-Z]{2,3}_[A-Z]{2,3}$')
            AND (split_part(game_id,'_',3)=stat_row->>'team' OR split_part(game_id,'_',4)=stat_row->>'team')
            AND stat_row->'passing_yards'='null'::jsonb AND stat_row->'rushing_yards'='null'::jsonb
            AND jsonb_typeof(stat_row->'receiving_yards')='number' AND jsonb_typeof(stat_row->'receptions')='number'
            AND (stat_row->>'receiving_yards')::numeric=trunc((stat_row->>'receiving_yards')::numeric)
            AND (stat_row->>'receptions')::numeric=trunc((stat_row->>'receptions')::numeric)
            AND abs((stat_row->>'receiving_yards')::numeric)<=10000
            AND (stat_row->>'receptions')::numeric BETWEEN 0 AND 10000
            AND ((stat_row->>'receptions')::numeric<>0 OR (stat_row->>'receiving_yards')::numeric=0)
            AND jsonb_typeof(manifest)='object'
            AND manifest ?& ARRAY['version','policy_version','bundle_sha256','game','explicit_source','explicit_source_sha256','stat_record_sha256']
            AND manifest->'version'='1'::jsonb
            AND manifest->'policy_version'=to_jsonb('nfl-explicit-receiving-v1'::text)
            AND manifest->'bundle_sha256'=to_jsonb(bundle_sha256)
            AND manifest->'stat_record_sha256'=to_jsonb(stat_record_sha256)
            AND jsonb_typeof(manifest->'game')='object'
            AND jsonb_typeof(manifest->'explicit_source')='object', false))
    )""")
    for table in TABLES:
        op.execute('ALTER TABLE public.'+table+' ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON public.'+table+' FROM PUBLIC')
        for role in ('anon','authenticated','sportsbet_dashboard'):
            op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
                'REVOKE ALL ON public.'+table+' FROM '+role+'; END IF; END $$')
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN "
            'REVOKE ALL ON public.'+table+' FROM sportsbet_worker; '
            'GRANT SELECT,INSERT ON public.'+table+' TO sportsbet_worker; '
            'CREATE POLICY sportsbet_worker_read ON public.'+table+' FOR SELECT TO sportsbet_worker USING (true); '
            'CREATE POLICY sportsbet_worker_insert ON public.'+table+' FOR INSERT TO sportsbet_worker WITH CHECK (true); '
            'END IF; END $$')


def downgrade():
    op.execute('DROP TABLE public.nfl_receiving_supplements')
    op.execute('DROP TABLE public.nfl_history_source_bundles')
