"""Private append-only paper-selection receipts with database-owned timing."""
from alembic import op
revision='0035_private_paper_receipts'
down_revision='0034_nfl_effective_history'
branch_labels=depends_on=None


def upgrade():
    op.execute('''CREATE TABLE analytics.paper_selections (
        protocol text NOT NULL,sport text NOT NULL CHECK(sport IN ('nba','nfl','cfb')),
        game_id text NOT NULL,player_id text NOT NULL,prediction_id text NOT NULL
            REFERENCES analytics.predictions(id),
        decision_at timestamptz NOT NULL,valid_until timestamptz NOT NULL,
        recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        payload text NOT NULL,payload_sha256 varchar(64) NOT NULL,
        PRIMARY KEY(protocol,sport,game_id,player_id),
        CHECK(decision_at<=recorded_at AND recorded_at<valid_until),
        CHECK(octet_length(payload) BETWEEN 1 AND 2000000
            AND jsonb_typeof(payload::jsonb)='object'
            AND payload_sha256=encode(sha256(convert_to(payload,'UTF8')),'hex'))
    )''')
    op.execute('''CREATE FUNCTION analytics.stamp_paper_receipt() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
        NEW.recorded_at=clock_timestamp(); RETURN NEW; END $$''')
    op.execute('''CREATE TRIGGER stamp_paper_receipt BEFORE INSERT ON analytics.paper_selections
        FOR EACH ROW EXECUTE FUNCTION analytics.stamp_paper_receipt()''')
    op.execute('ALTER TABLE analytics.paper_selections ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON analytics.paper_selections FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION analytics.stamp_paper_receipt() FROM PUBLIC')
    for role in ('anon','authenticated','sportsbet_dashboard'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            'REVOKE ALL ON analytics.paper_selections FROM '+role+'; END IF; END $$')
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        REVOKE ALL ON analytics.paper_selections FROM sportsbet_worker;
        GRANT SELECT,INSERT ON analytics.paper_selections TO sportsbet_worker;
        CREATE POLICY sportsbet_worker_paper ON analytics.paper_selections TO sportsbet_worker
            USING(true) WITH CHECK(true); END IF; END $$""")


def downgrade():
    op.execute('DROP TABLE analytics.paper_selections')
    op.execute('DROP FUNCTION analytics.stamp_paper_receipt()')
