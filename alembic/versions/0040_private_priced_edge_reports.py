"""Allow the existing append-only private table to retain priced NFL edge audits."""
from alembic import op

revision = '0040_private_priced_edge_reports'
down_revision = '0039_prediction_record_receipts'
branch_labels = depends_on = None

OLD = 'nfl-receiving-individual-pick-audit-v1'
NEW = 'nfl-priced-prospective-checkpoint-v1'
CURRENT = 'nfl-history-priced-prospective-v1'


def upgrade():
    op.execute('''ALTER TABLE analytics.prospective_audit_reports
        DROP CONSTRAINT prospective_audit_reports_protocol_check''')
    op.execute(f'''ALTER TABLE analytics.prospective_audit_reports
        ADD CONSTRAINT ck_private_prospective_report_protocol
        CHECK (protocol IN ('{OLD}', '{NEW}', '{CURRENT}'))''')


def downgrade():
    # Never silently erase an append-only private research result.
    op.execute(f'''DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM analytics.prospective_audit_reports
                   WHERE protocol IN ('{NEW}', '{CURRENT}')) THEN
            RAISE EXCEPTION 'Cannot downgrade with retained priced edge reports';
        END IF;
    END $$''')
    op.execute('''ALTER TABLE analytics.prospective_audit_reports
        DROP CONSTRAINT ck_private_prospective_report_protocol''')
    op.execute(f'''ALTER TABLE analytics.prospective_audit_reports
        ADD CONSTRAINT prospective_audit_reports_protocol_check
        CHECK (protocol = '{OLD}')''')
