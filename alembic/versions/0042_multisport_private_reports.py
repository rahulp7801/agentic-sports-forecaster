"""Allow private NBA and corrected-CFB priced reports in the append-only table."""
from alembic import op

revision = '0042_multisport_private_reports'
down_revision = '0041_cfb_dashboard_versions'
branch_labels = depends_on = None

OLD = ('nfl-receiving-individual-pick-audit-v1',
       'nfl-priced-prospective-checkpoint-v1',
       'nfl-history-priced-prospective-v1')
NEW = ('nba-cfb-priced-prospective-v1', 'cfb-history-priced-prospective-v1')


def _constraint(values):
    return ', '.join("'" + value + "'" for value in values)


def upgrade():
    op.execute('ALTER TABLE analytics.prospective_audit_reports '
               'DROP CONSTRAINT ck_private_prospective_report_protocol')
    op.execute('ALTER TABLE analytics.prospective_audit_reports '
               'ADD CONSTRAINT ck_private_prospective_report_protocol '
               f'CHECK (protocol IN ({_constraint(OLD + NEW)}))')


def downgrade():
    # Keep every private result; refuse a rollback that would invalidate a row.
    op.execute(f'''DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM analytics.prospective_audit_reports
                   WHERE protocol IN ({_constraint(NEW)})) THEN
            RAISE EXCEPTION 'Cannot downgrade with retained NBA/CFB reports';
        END IF;
    END $$''')
    op.execute('ALTER TABLE analytics.prospective_audit_reports '
               'DROP CONSTRAINT ck_private_prospective_report_protocol')
    op.execute('ALTER TABLE analytics.prospective_audit_reports '
               'ADD CONSTRAINT ck_private_prospective_report_protocol '
               f'CHECK (protocol IN ({_constraint(OLD)}))')
