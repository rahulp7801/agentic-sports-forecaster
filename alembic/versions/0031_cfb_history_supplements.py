"""Retain append-only CFB final-stat supplements behind restricted access."""
from alembic import op

revision = '0031_cfb_history_supplements'
down_revision = '0030_gamelog_player_identity'
branch_labels = depends_on = None

TABLES = ('cfb_history_source_bundles', 'cfb_receiving_supplements')
VIEW = 'cfb_effective_gamelogs'
# Frozen schema constants; never import mutable application field maps in a migration.
FIELDS = ('id','athlete_id','game_id','season','week','game_date','player_name','team_id',
    'team_name','team_abbreviation','opponent_id','opponent_name','opponent_abbreviation',
    'is_home','passing_yards','rushing_yards','receiving_yards','receptions',
    'source_provider','source_sha256','source_player_sha256','source_schedule_sha256',
    'source_record_sha256','source_observed_at')


def upgrade():
    op.execute("""CREATE TABLE public.cfb_history_source_bundles (
        bundle_sha256 varchar(64) PRIMARY KEY,
        response_text text NOT NULL,
        archived_at timestamptz NOT NULL DEFAULT now(),
        CHECK (octet_length(response_text) BETWEEN 1 AND 25000000
            AND jsonb_typeof(response_text::jsonb)='object'
            AND bundle_sha256=encode(sha256(convert_to(response_text,'UTF8')),'hex'))
    )""")
    op.execute("""CREATE TABLE public.cfb_receiving_supplements (
        athlete_id bigint NOT NULL CHECK (athlete_id>0),
        game_id varchar(20) NOT NULL CHECK (game_id ~ '^[1-9][0-9]{0,14}$'),
        primary_record_sha256 varchar(64) NOT NULL CHECK (primary_record_sha256 ~ '^[0-9a-f]{64}$'),
        bundle_sha256 varchar(64) NOT NULL REFERENCES public.cfb_history_source_bundles(bundle_sha256),
        primary_row jsonb NOT NULL,
        receiving_yards integer NOT NULL CHECK (abs(receiving_yards)<=10000),
        receptions integer NOT NULL CHECK (receptions BETWEEN 0 AND 10000),
        effective_record_sha256 varchar(64) NOT NULL CHECK (effective_record_sha256 ~ '^[0-9a-f]{64}$'),
        source_sha256 varchar(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
        manifest jsonb NOT NULL,
        observed_at timestamptz NOT NULL,
        inserted_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(athlete_id,game_id,primary_record_sha256),
        CHECK (jsonb_typeof(primary_row)='object' AND jsonb_typeof(manifest)='object'
            AND primary_row ?& ARRAY['game_id','athlete_id','player_name','team_id',
                'passing_yards','rushing_yards','receiving_yards','receptions','season','week',
                'game_date','is_home','team_name','team_abbreviation','opponent_id',
                'opponent_name','opponent_abbreviation']
            AND primary_row->'athlete_id'=to_jsonb(athlete_id)
            AND primary_row->'game_id'=to_jsonb(game_id)
            AND manifest ?& ARRAY['version','policy_version','primary_record_sha256','bundle_sha256',
                'effective_record_sha256','supplemented_fields','explicit_source']
            AND manifest->'version'='1'::jsonb
            AND manifest->'policy_version'=to_jsonb('cfb-explicit-receiving-v1'::text)
            AND manifest->'primary_record_sha256'=to_jsonb(primary_record_sha256)
            AND manifest->'bundle_sha256'=to_jsonb(bundle_sha256)
            AND manifest->'effective_record_sha256'=to_jsonb(effective_record_sha256)
            AND jsonb_typeof(manifest->'supplemented_fields')='object'
            AND manifest->'supplemented_fields'<>'{}'::jsonb
            AND (manifest->'supplemented_fields')-'receiving_yards'-'receptions'='{}'::jsonb
            AND ((primary_row->>'receiving_yards') IS NULL)=(manifest->'supplemented_fields' ? 'receiving_yards')
            AND ((primary_row->>'receptions') IS NULL)=(manifest->'supplemented_fields' ? 'receptions')
            AND COALESCE((primary_row->>'receiving_yards')::int,receiving_yards)=receiving_yards
            AND COALESCE((primary_row->>'receptions')::int,receptions)=receptions
            AND COALESCE((manifest->'supplemented_fields'->>'receiving_yards')::int,receiving_yards)=receiving_yards
            AND COALESCE((manifest->'supplemented_fields'->>'receptions')::int,receptions)=receptions
            AND (receptions<>0 OR receiving_yards=0))
    )""")
    overrides = dict(receiving_yards='COALESCE(s.receiving_yards,p.receiving_yards)',
        receptions='COALESCE(s.receptions,p.receptions)',
        source_provider="CASE WHEN s.athlete_id IS NOT NULL THEN 'sportsdataverse_espn_supplement' ELSE p.source_provider END",
        source_sha256='COALESCE(s.source_sha256,p.source_sha256)',
        source_record_sha256='COALESCE(s.effective_record_sha256,p.source_record_sha256)',
        source_observed_at='COALESCE(s.observed_at,p.source_observed_at)')
    selections = [overrides.get(f, 'p.'+f)+' AS '+f for f in FIELDS]
    op.execute('CREATE VIEW public.'+VIEW+' WITH (security_barrier=true) AS SELECT '
        + ','.join(selections) + ",s.manifest AS supplement_manifest,"
        "CASE WHEN s.athlete_id IS NOT NULL THEN 'cfb-explicit-receiving-v1' ELSE 'primary-v1' END AS history_policy_version "
        'FROM public.cfb_player_gamelogs p LEFT JOIN public.cfb_receiving_supplements s '
        'ON s.athlete_id=p.athlete_id AND s.game_id=p.game_id '
        'AND s.primary_record_sha256=p.source_record_sha256 '
        "AND p.source_provider='sportsdataverse_espn' AND to_jsonb(p) @> s.primary_row")
    for table in TABLES:
        op.execute('ALTER TABLE public.'+table+' ENABLE ROW LEVEL SECURITY')
    for target in (*TABLES, VIEW):
        op.execute('REVOKE ALL ON public.'+target+' FROM PUBLIC')
        for role in ('anon','authenticated','sportsbet_dashboard'):
            op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
                'REVOKE ALL ON public.'+target+' FROM '+role+'; END IF; END $$')
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN "
            'REVOKE ALL ON public.'+target+' FROM sportsbet_worker; '
            'GRANT SELECT ON public.'+target+' TO sportsbet_worker; END IF; END $$')
    for table in TABLES:
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN "
            'GRANT INSERT ON public.'+table+' TO sportsbet_worker; '
            'CREATE POLICY sportsbet_worker_read ON public.'+table+' FOR SELECT TO sportsbet_worker USING (true); '
            'CREATE POLICY sportsbet_worker_insert ON public.'+table+' FOR INSERT TO sportsbet_worker WITH CHECK (true); '
            'END IF; END $$')


def downgrade():
    op.execute('DROP VIEW public.'+VIEW)
    op.execute('DROP TABLE public.cfb_receiving_supplements')
    op.execute('DROP TABLE public.cfb_history_source_bundles')
