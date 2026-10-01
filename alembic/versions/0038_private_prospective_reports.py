"""Store frozen prospective audit reports privately and append-only."""
from alembic import op

revision = '0038_private_prospective_reports'
down_revision = '0037_cfb_primary_revisions'
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE analytics.prospective_audit_reports (
        report_id BIGSERIAL PRIMARY KEY,
        protocol TEXT NOT NULL
            CHECK (protocol = 'nfl-receiving-individual-pick-audit-v1'),
        observed_at TIMESTAMPTZ NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        payload TEXT NOT NULL,
        payload_sha256 VARCHAR(64) NOT NULL,
        CHECK (octet_length(payload) BETWEEN 1 AND 2000000
            AND jsonb_typeof(payload::jsonb) = 'object'
            AND payload::jsonb #>> '{protocol,version}' = protocol
            AND (payload::jsonb->>'observed_at')::timestamptz = observed_at
            AND payload_sha256 = encode(sha256(convert_to(payload,'UTF8')),'hex'))
    )""")
    op.execute("""CREATE FUNCTION analytics.stamp_prospective_audit_report()
        RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN
            NEW.recorded_at = clock_timestamp();
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER stamp_prospective_audit_report
        BEFORE INSERT ON analytics.prospective_audit_reports
        FOR EACH ROW EXECUTE FUNCTION analytics.stamp_prospective_audit_report()""")
    op.execute('REVOKE ALL ON analytics.prospective_audit_reports FROM PUBLIC')
    op.execute('REVOKE ALL ON SEQUENCE analytics.prospective_audit_reports_report_id_seq FROM PUBLIC')
    op.execute('REVOKE ALL ON FUNCTION analytics.stamp_prospective_audit_report() FROM PUBLIC')
    op.execute('ALTER TABLE analytics.prospective_audit_reports ENABLE ROW LEVEL SECURITY')
    for role in ('anon', 'authenticated', 'sportsbet_dashboard'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            'REVOKE ALL ON analytics.prospective_audit_reports FROM '+role+'; '
            'REVOKE ALL ON SEQUENCE analytics.prospective_audit_reports_report_id_seq FROM '+role+'; '
            'END IF; END $$')
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sportsbet_worker') THEN
        GRANT USAGE ON SCHEMA analytics TO sportsbet_worker;
        GRANT SELECT,INSERT ON analytics.prospective_audit_reports TO sportsbet_worker;
        GRANT USAGE,SELECT ON SEQUENCE analytics.prospective_audit_reports_report_id_seq TO sportsbet_worker;
        CREATE POLICY worker_read_prospective_reports ON analytics.prospective_audit_reports
            FOR SELECT TO sportsbet_worker USING (true);
        CREATE POLICY worker_insert_prospective_reports ON analytics.prospective_audit_reports
            FOR INSERT TO sportsbet_worker WITH CHECK (true);
    END IF; END $$""")


def downgrade():
    op.execute('DROP TABLE analytics.prospective_audit_reports')
    op.execute('DROP FUNCTION analytics.stamp_prospective_audit_report()')
