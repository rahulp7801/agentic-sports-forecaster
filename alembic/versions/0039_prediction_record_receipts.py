"""Stamp future prediction rows at insert without falsifying legacy timing."""
from alembic import op

revision = '0039_prediction_record_receipts'
down_revision = '0038_private_prospective_reports'
branch_labels = depends_on = None


def upgrade():
    # No default: old forecasts predate this evidence boundary and remain unknown.
    op.execute('ALTER TABLE analytics.predictions ADD COLUMN recorded_at TIMESTAMPTZ')
    op.execute('ALTER TABLE analytics.predictions ADD COLUMN payload_sha256 VARCHAR(64)')
    op.execute("""ALTER TABLE analytics.predictions ADD CONSTRAINT ck_prediction_record_commitment
        CHECK ((recorded_at IS NULL AND payload_sha256 IS NULL) OR
            (recorded_at IS NOT NULL AND payload_sha256 IS NOT NULL AND payload_sha256 =
                encode(sha256(convert_to(payload,'UTF8')),'hex')))""")
    op.execute("""CREATE FUNCTION analytics.stamp_prediction_record()
        RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                NEW.recorded_at = clock_timestamp();
                NEW.payload_sha256 = encode(sha256(convert_to(NEW.payload,'UTF8')),'hex');
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Prediction source record is immutable';
            ELSIF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.scan_id IS DISTINCT FROM OLD.scan_id
                OR NEW.payload IS DISTINCT FROM OLD.payload
                OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
                OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 THEN
                RAISE EXCEPTION 'Prediction source record is immutable';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER stamp_prediction_record
        BEFORE INSERT OR UPDATE OR DELETE ON analytics.predictions
        FOR EACH ROW EXECUTE FUNCTION analytics.stamp_prediction_record()""")
    op.execute('REVOKE ALL ON FUNCTION analytics.stamp_prediction_record() FROM PUBLIC')
    for role in ('anon', 'authenticated', 'sportsbet_dashboard'):
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"+role+"') THEN "
            'REVOKE ALL ON FUNCTION analytics.stamp_prediction_record() FROM '+role+'; '
            'END IF; END $$')


def downgrade():
    op.execute('DROP TRIGGER stamp_prediction_record ON analytics.predictions')
    op.execute('DROP FUNCTION analytics.stamp_prediction_record()')
    op.execute('ALTER TABLE analytics.predictions DROP CONSTRAINT ck_prediction_record_commitment')
    op.execute('ALTER TABLE analytics.predictions DROP COLUMN recorded_at,DROP COLUMN payload_sha256')
