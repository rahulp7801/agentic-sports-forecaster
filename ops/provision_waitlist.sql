-- Run through the existing production migration gate after 0046_private_waitlist.
-- The protected production-schema job runs ops/provision_waitlist.py automatically.
-- This SQL is retained only as a readable grant specification for disposable ACL tests.
-- This role must be newly created, not a dashboard/worker/provider role.
GRANT USAGE ON SCHEMA private_access TO sportsbet_waitlist_writer;
GRANT EXECUTE ON FUNCTION private_access.join_waitlist(text) TO sportsbet_waitlist_writer;
REVOKE ALL ON ALL TABLES IN SCHEMA private_access FROM sportsbet_waitlist_writer;
