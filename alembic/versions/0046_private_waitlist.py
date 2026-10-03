"""Retain consented waitlist emails behind one narrow server-only write function."""
from alembic import op

revision = '0046_private_waitlist'
down_revision = '0045_nfl_core_history_revisions'
branch_labels = depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA private_access")
    op.execute("REVOKE ALL ON SCHEMA private_access FROM PUBLIC")
    op.execute("""CREATE TABLE private_access.waitlist (
        email text PRIMARY KEY CHECK (email=lower(btrim(email)) AND length(email)<=254),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        consent_version text NOT NULL DEFAULT 'access-update-v1'
            CHECK (consent_version='access-update-v1'))""")
    op.execute("""CREATE TABLE private_access.waitlist_limits (
        period text NOT NULL CHECK (period IN ('minute','day')),
        bucket bigint NOT NULL, requests integer NOT NULL CHECK (requests>0),
        PRIMARY KEY(period,bucket))""")
    op.execute("ALTER TABLE private_access.waitlist ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE private_access.waitlist_limits ENABLE ROW LEVEL SECURITY")
    op.execute("""CREATE FUNCTION private_access.join_waitlist(address text) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
        DECLARE moment bigint; minute_count integer; day_count integer;
        BEGIN
          IF address IS NULL OR address<>lower(btrim(address)) OR length(address)>254
             OR address !~ '^[a-z0-9.!#$%&''*+/=?^_`{|}~-]{1,64}@[a-z0-9]([a-z0-9-]*[a-z0-9])?([.][a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' THEN
            RAISE EXCEPTION 'Invalid waitlist input';
          END IF;
          PERFORM pg_catalog.pg_advisory_xact_lock(20261006,46);
          moment := floor(extract(epoch FROM clock_timestamp()));
          -- Durable global ceilings survive deployments, retries and separate server instances.
          INSERT INTO private_access.waitlist_limits(period,bucket,requests) VALUES ('minute',moment/60,1)
            ON CONFLICT(period,bucket) DO UPDATE SET requests=private_access.waitlist_limits.requests+1
            RETURNING requests INTO minute_count;
          INSERT INTO private_access.waitlist_limits(period,bucket,requests) VALUES ('day',moment/86400,1)
            ON CONFLICT(period,bucket) DO UPDATE SET requests=private_access.waitlist_limits.requests+1
            RETURNING requests INTO day_count;
          DELETE FROM private_access.waitlist_limits WHERE bucket <
            CASE period WHEN 'minute' THEN moment/60-2 ELSE moment/86400-2 END;
          IF minute_count>30 OR day_count>500 THEN RETURN false; END IF;
          INSERT INTO private_access.waitlist(email) VALUES(address) ON CONFLICT(email) DO NOTHING;
          RETURN true;
        END $function$""")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA private_access FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION private_access.join_waitlist(text) FROM PUBLIC")
    # Explicit provider/browser defaults may grant privileges independently of PUBLIC.
    op.execute("""DO $$ DECLARE role_name text; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','sportsbet_dashboard','sportsbet_worker'] LOOP
          IF EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=role_name) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA private_access FROM %I',role_name);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA private_access FROM %I',role_name);
            EXECUTE format('REVOKE ALL ON FUNCTION private_access.join_waitlist(text) FROM %I',role_name);
          END IF;
        END LOOP;
    END $$""")


def downgrade():
    # Never silently delete an actual signup or its consent record.
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM private_access.waitlist) THEN
          RAISE EXCEPTION 'Cannot downgrade with retained waitlist entries';
        END IF;
    END $$""")
    op.execute("DROP FUNCTION private_access.join_waitlist(text)")
    op.execute("DROP TABLE private_access.waitlist_limits")
    op.execute("DROP TABLE private_access.waitlist")
    op.execute("DROP SCHEMA private_access")
