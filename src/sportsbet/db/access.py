"""Provision separate snapshot-reader and ingestion roles; never export owner credentials."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from sportsbet.config import settings

READER = 'sportsbet_dashboard'
WORKER = 'sportsbet_worker'
READ_TABLES = ('games', 'player_stats', 'nfl_snap_counts', 'cfb_player_gamelogs', 'nba_player_gamelogs', 'nba_player_stats',
               'play_by_play', 'ngs_stats', 'injury_reports', 'odds_snapshots',
               'player_prop_snapshots', 'dashboard_snapshots', 'cfb_history_source_bundles', 'cfb_receiving_supplements',
               'nfl_history_source_bundles', 'nfl_receiving_supplements')
WRITE_TABLES = ('games', 'player_stats', 'nfl_snap_counts', 'cfb_player_gamelogs',
                'nba_player_gamelogs', 'ngs_stats', 'dashboard_snapshots')
APPEND_TABLES = ('odds_snapshots', 'player_prop_snapshots', 'cfb_history_source_bundles', 'cfb_receiving_supplements',
               'nfl_history_source_bundles', 'nfl_receiving_supplements')
CACHE_TABLES = ('provider_response_cache',)
ANALYTICS_TABLES = ('predictions', 'exposure', 'quotes', 'api_usage', 'paper_selections')
PRIVATE_REPORT_TABLE = 'prospective_audit_reports'
OPTIONAL_PRIVATE_TABLES = ('nfl_primary_revisions', 'ngs_partition_versions', 'ngs_partition_rows',
                           'nba_participation_versions')
OPTIONAL_WORKER_VIEWS = ('ngs_partition_catalog', 'ngs_history_versions')
NGS_REPLACE_FUNCTION = 'public.replace_ngs_partition(integer,text,text,timestamp with time zone,jsonb)'
OPTIONAL_DASHBOARD_VIEWS = ('dashboard_gamelogs_asof', 'dashboard_gamelog_versions',
                            'dashboard_nfl_core_gamelogs_asof')


def _revoke_private_columns(conn,table,grantees):
    # PostgreSQL column grants survive a table-level REVOKE. Clear them before
    # restoring the worker's explicit append columns and read permission.
    columns=conn.execute('SELECT attname FROM pg_attribute WHERE attrelid=to_regclass(%s) '
        'AND attnum>0 AND NOT attisdropped ORDER BY attnum',(f'public.{table}',)).fetchall()
    if columns:
        conn.execute(sql.SQL('REVOKE ALL ({}) ON {} FROM {}').format(
            sql.SQL(', ').join(sql.Identifier(name) for (name,) in columns),
            sql.Identifier('public',table),sql.SQL(', ').join(grantees)))


def deny_browser_roles(conn):
    """Supabase defaults can grant named browser roles independently of PUBLIC/RLS."""
    targets: list[sql.Composable] = [sql.Identifier('public', table) for table in
                                     (*READ_TABLES, *CACHE_TABLES, 'alembic_version',
                                      'ev_signals', 'dashboard_gamelogs', 'cfb_effective_gamelogs', 'nfl_effective_receiving_gamelogs')]
    targets.extend(sql.Identifier('public', table) for table in (*OPTIONAL_DASHBOARD_VIEWS, *OPTIONAL_PRIVATE_TABLES, *OPTIONAL_WORKER_VIEWS)
                   if conn.execute('SELECT to_regclass(%s)', (f'public.{table}',)).fetchone()[0])
    targets.extend(sql.Identifier('analytics', table) for table in (*ANALYTICS_TABLES, PRIVATE_REPORT_TABLE))
    grantees: list[sql.Composable] = [sql.SQL('PUBLIC')]
    for role in ('anon', 'authenticated'):
        if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
            grantees.append(sql.Identifier(role))
    # Defaults belong to the connected application creator, not provider-admin roles.
    for schema in ('public', 'analytics'):
        for kind in ('TABLES', 'SEQUENCES'):
            conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE ALL ON {} FROM {}').format(
                sql.Identifier(schema), sql.SQL(kind), sql.SQL(', ').join(grantees)))
    conn.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(
        sql.SQL(', ').join(targets), sql.SQL(', ').join(grantees)))
    conn.execute(sql.SQL('REVOKE ALL ON SEQUENCE analytics.prospective_audit_reports_report_id_seq FROM {}')
                 .format(sql.SQL(', ').join(grantees)))
    for table in OPTIONAL_PRIVATE_TABLES:
        if conn.execute('SELECT to_regclass(%s)',(f'public.{table}',)).fetchone()[0]:
            _revoke_private_columns(conn,table,grantees)
            for (sequence,) in conn.execute("SELECT pg_get_serial_sequence(%s,column_name) "
                    "FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                    (f'public.{table}',table)).fetchall():
                if sequence:
                    schema,name=sequence.split('.',1)
                    conn.execute(sql.SQL('REVOKE ALL ON SEQUENCE {} FROM {}').format(
                        sql.Identifier(schema,name),sql.SQL(', ').join(grantees)))
    if conn.execute('SELECT to_regprocedure(%s)', (NGS_REPLACE_FUNCTION,)).fetchone()[0]:
        conn.execute(sql.SQL('REVOKE ALL ON FUNCTION {} FROM {}').format(
            sql.SQL(NGS_REPLACE_FUNCTION), sql.SQL(', ').join(grantees)))
    if conn.execute("SELECT to_regprocedure('public.capture_nba_participation_version()')").fetchone()[0]:
        conn.execute(sql.SQL('REVOKE ALL ON FUNCTION public.capture_nba_participation_version() FROM {}')
            .format(sql.SQL(', ').join(grantees)))


def _lock_policy_tables(conn):
    """Acquire policy-table locks before role/catalog writes can form a deadlock."""
    targets = [sql.Identifier('public', 'alembic_version')]
    targets.extend(sql.Identifier('public', table) for table in READ_TABLES)
    targets.extend(sql.Identifier('public', table) for table in CACHE_TABLES)
    targets.extend(sql.Identifier('analytics', table) for table in (*ANALYTICS_TABLES, PRIVATE_REPORT_TABLE))
    conn.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(sql.SQL(', ').join(targets)))


def apply_access(conn):
    """Explicit grants and role-specific RLS policies; no rights for anonymous users."""
    deny_browser_roles(conn)
    for table in OPTIONAL_PRIVATE_TABLES:
        if conn.execute('SELECT to_regclass(%s)', (f'public.{table}',)).fetchone()[0]:
            for role in (READER, WORKER):
                conn.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(
                    sql.Identifier('public', table), sql.Identifier(role)))
                _revoke_private_columns(conn,table,[sql.Identifier(role)])
                for (sequence,) in conn.execute("SELECT pg_get_serial_sequence(%s,column_name) "
                        "FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                        (f'public.{table}',table)).fetchall():
                    if sequence:
                        schema,name=sequence.split('.',1)
                        conn.execute(sql.SQL('REVOKE ALL ON SEQUENCE {} FROM {}').format(
                            sql.Identifier(schema,name), sql.Identifier(role)))
    # Archive writes use fixed owner-executed functions/triggers. Participation
    # later receives only explicit append columns, without receipt mutation.
    conn.execute(sql.SQL('GRANT SELECT ON public.alembic_version TO {}').format(sql.Identifier(WORKER)))
    conn.execute('DROP POLICY IF EXISTS sportsbet_worker_schema_readiness ON public.alembic_version')
    conn.execute(sql.SQL('CREATE POLICY sportsbet_worker_schema_readiness ON public.alembic_version '
                         'FOR SELECT TO {} USING (true)').format(sql.Identifier(WORKER)))
    conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}, {}').format(sql.Identifier(READER), sql.Identifier(WORKER)))
    conn.execute(sql.SQL('GRANT SELECT ON public.dashboard_snapshots TO {}').format(sql.Identifier(READER)))
    conn.execute(sql.SQL('GRANT SELECT ON public.dashboard_gamelogs TO {}').format(sql.Identifier(READER)))
    # Role provisioning may happen after migrations; restore versioned-view
    # grants in that order as well as when migrations run against existing roles.
    for table in OPTIONAL_DASHBOARD_VIEWS:
        if conn.execute('SELECT to_regclass(%s)', (f'public.{table}',)).fetchone()[0]:
            conn.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(
                sql.Identifier('public', table), sql.Identifier(READER)))
    conn.execute(sql.SQL('GRANT SELECT ON public.cfb_effective_gamelogs TO {}').format(sql.Identifier(WORKER)))
    conn.execute(sql.SQL('GRANT SELECT ON public.nfl_effective_receiving_gamelogs TO {}').format(sql.Identifier(WORKER)))
    for table in READ_TABLES:
        target = sql.Identifier('public', table)
        conn.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(target, sql.Identifier(WORKER)))
        conn.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(target))
        conn.execute(sql.SQL('DROP POLICY IF EXISTS sportsbet_worker_read ON {}').format(target))
        conn.execute(sql.SQL('CREATE POLICY sportsbet_worker_read ON {} FOR SELECT TO {} USING (true)').format(target, sql.Identifier(WORKER)))
    conn.execute('DROP POLICY IF EXISTS sportsbet_dashboard_read ON public.dashboard_snapshots')
    conn.execute(sql.SQL('CREATE POLICY sportsbet_dashboard_read ON public.dashboard_snapshots FOR SELECT TO {} USING (true)').format(sql.Identifier(READER)))
    for table in WRITE_TABLES:
        target = sql.Identifier('public', table)
        conn.execute(sql.SQL('GRANT INSERT, UPDATE ON {} TO {}').format(target, sql.Identifier(WORKER)))
        for command in ('INSERT', 'UPDATE'):
            policy = sql.Identifier('sportsbet_worker_' + command.lower())
            conn.execute(sql.SQL('DROP POLICY IF EXISTS {} ON {}').format(policy, target))
            clause = sql.SQL('WITH CHECK (true)' if command == 'INSERT' else 'USING (true) WITH CHECK (true)')
            conn.execute(sql.SQL('CREATE POLICY {} ON {} FOR {} TO {} {}').format(policy, target, sql.SQL(command), sql.Identifier(WORKER), clause))
    # NGS refreshes replace one season/stat partition atomically so rows removed
    # by the upstream release cannot remain in the evidence table.
    conn.execute(sql.SQL('GRANT DELETE ON public.ngs_stats TO {}').format(sql.Identifier(WORKER)))
    conn.execute('DROP POLICY IF EXISTS sportsbet_worker_delete ON public.ngs_stats')
    conn.execute(sql.SQL('CREATE POLICY sportsbet_worker_delete ON public.ngs_stats '
                         'FOR DELETE TO {} USING (true)').format(sql.Identifier(WORKER)))
    for table in ('cfb_history_source_bundles', 'cfb_receiving_supplements',
               'nfl_history_source_bundles', 'nfl_receiving_supplements'):
        conn.execute(sql.SQL('REVOKE UPDATE, DELETE, TRUNCATE ON {} FROM {}').format(
            sql.Identifier('public', table), sql.Identifier(WORKER)))
    for table in APPEND_TABLES:
        target = sql.Identifier('public', table)
        conn.execute(sql.SQL('GRANT INSERT ON {} TO {}').format(target, sql.Identifier(WORKER)))
        conn.execute(sql.SQL('DROP POLICY IF EXISTS sportsbet_worker_insert ON {}').format(target))
        conn.execute(sql.SQL('CREATE POLICY sportsbet_worker_insert ON {} FOR INSERT TO {} WITH CHECK (true)')
                     .format(target, sql.Identifier(WORKER)))
    for table in CACHE_TABLES:
        target = sql.Identifier('public', table)
        conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE ON {} TO {}').format(target, sql.Identifier(WORKER)))
        conn.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(target))
        for command in ('SELECT', 'INSERT', 'UPDATE'):
            policy = sql.Identifier('sportsbet_worker_' + command.lower())
            conn.execute(sql.SQL('DROP POLICY IF EXISTS {} ON {}').format(policy, target))
            clause = sql.SQL('USING (true)' if command == 'SELECT' else
                'WITH CHECK (true)' if command == 'INSERT' else 'USING (true) WITH CHECK (true)')
            conn.execute(sql.SQL('CREATE POLICY {} ON {} FOR {} TO {} {}').format(
                policy, target, sql.SQL(command), sql.Identifier(WORKER), clause))
    conn.execute(sql.SQL('GRANT USAGE ON SCHEMA analytics TO {}').format(sql.Identifier(WORKER)))
    for table in ANALYTICS_TABLES:
        target = sql.Identifier('analytics', table)
        conn.execute(sql.SQL('GRANT SELECT, INSERT ON {} TO {}').format(target, sql.Identifier(WORKER)))
        conn.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(target))
        conn.execute(sql.SQL('DROP POLICY IF EXISTS sportsbet_worker_access ON {}').format(target))
        conn.execute(sql.SQL('CREATE POLICY sportsbet_worker_access ON {} TO {} USING (true) WITH CHECK (true)').format(target, sql.Identifier(WORKER)))
    conn.execute(sql.SQL('REVOKE UPDATE, DELETE, TRUNCATE ON analytics.paper_selections FROM {}').format(sql.Identifier(WORKER)))
    # Migrations may run before roles are first provisioned. Restore the
    # private audit table's append-only ACL and RLS policies in either order.
    conn.execute(sql.SQL('GRANT SELECT, INSERT ON analytics.prospective_audit_reports TO {}')
                 .format(sql.Identifier(WORKER)))
    conn.execute(sql.SQL('GRANT USAGE, SELECT ON SEQUENCE analytics.prospective_audit_reports_report_id_seq TO {}')
                 .format(sql.Identifier(WORKER)))
    conn.execute(sql.SQL('REVOKE UPDATE, DELETE, TRUNCATE ON analytics.prospective_audit_reports FROM {}')
                 .format(sql.Identifier(WORKER)))
    conn.execute('ALTER TABLE analytics.prospective_audit_reports ENABLE ROW LEVEL SECURITY')
    for command in ('SELECT', 'INSERT'):
        policy = sql.Identifier('worker_' + ('read' if command == 'SELECT' else 'insert') + '_prospective_reports')
        conn.execute(sql.SQL('DROP POLICY IF EXISTS {} ON analytics.prospective_audit_reports').format(policy))
        clause = sql.SQL('USING (true)' if command == 'SELECT' else 'WITH CHECK (true)')
        conn.execute(sql.SQL('CREATE POLICY {} ON analytics.prospective_audit_reports FOR {} TO {} {}')
                     .format(policy, sql.SQL(command), sql.Identifier(WORKER), clause))
    conn.execute(sql.SQL('GRANT UPDATE (outcome,outcome_source,outcome_ref,outcome_observed_at,actual_value,outcome_evidence) ON analytics.predictions TO {}').format(sql.Identifier(WORKER)))
    for table in ('exposure', 'api_usage'):
        conn.execute(sql.SQL('GRANT UPDATE ON {} TO {}').format(sql.Identifier('analytics', table), sql.Identifier(WORKER)))
    # Only sequences attached to writable public tables, not every current/future sequence.
    for table in (*WRITE_TABLES, *APPEND_TABLES):
        rows = conn.execute("SELECT pg_get_serial_sequence(%s, column_name) FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=%s", (f'public.{table}', table)).fetchall()
        for (sequence,) in rows:
            if sequence:
                schema, name = sequence.split('.', 1)
                conn.execute(sql.SQL('GRANT USAGE, SELECT ON SEQUENCE {} TO {}').format(sql.Identifier(schema, name), sql.Identifier(WORKER)))
    # Keep the same narrow replacement boundary when roles are provisioned or
    # repaired after the history migration. Readers never receive these views.
    for table in OPTIONAL_WORKER_VIEWS:
        if conn.execute('SELECT to_regclass(%s)', (f'public.{table}',)).fetchone()[0]:
            conn.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(
                sql.Identifier('public',table),sql.Identifier(READER)))
            conn.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(
                sql.Identifier('public',table),sql.Identifier(WORKER)))
    if conn.execute('SELECT to_regprocedure(%s)', (NGS_REPLACE_FUNCTION,)).fetchone()[0]:
        conn.execute(sql.SQL('REVOKE ALL ON FUNCTION {} FROM {}').format(
            sql.SQL(NGS_REPLACE_FUNCTION),sql.Identifier(READER)))
        conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION {} TO {}').format(
            sql.SQL(NGS_REPLACE_FUNCTION),sql.Identifier(WORKER)))
        conn.execute(sql.SQL('REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON public.ngs_stats FROM {}')
            .format(sql.Identifier(WORKER)))
    if conn.execute("SELECT to_regclass('public.nba_participation_versions')").fetchone()[0]:
        conn.execute('ALTER TABLE public.nba_participation_versions ENABLE ROW LEVEL SECURITY')
        conn.execute(sql.SQL('GRANT SELECT ON public.nba_participation_versions TO {}').format(sql.Identifier(WORKER)))
        conn.execute(sql.SQL('GRANT INSERT (player_id,player_name,game_id,game_date,season,team_abbreviation,minutes,'
            'source_provider,source_sha256,source_record_sha256,source_observed_at) '
            'ON public.nba_participation_versions TO {}').format(sql.Identifier(WORKER)))
        conn.execute(sql.SQL('GRANT USAGE ON SEQUENCE public.nba_participation_versions_version_id_seq TO {}')
            .format(sql.Identifier(WORKER)))
        for command in ('SELECT','INSERT'):
            policy=sql.Identifier('sportsbet_worker_'+('read' if command=='SELECT' else 'insert'))
            conn.execute(sql.SQL('DROP POLICY IF EXISTS {} ON public.nba_participation_versions').format(policy))
            clause=sql.SQL('USING (true)' if command=='SELECT' else 'WITH CHECK (true)')
            conn.execute(sql.SQL('CREATE POLICY {} ON public.nba_participation_versions FOR {} TO {} {}')
                .format(policy,sql.SQL(command),sql.Identifier(WORKER),clause))
        conn.execute(sql.SQL('REVOKE ALL ON FUNCTION public.capture_nba_participation_version() FROM {},{}')
            .format(sql.Identifier(READER),sql.Identifier(WORKER)))


def provision_roles(conn, passwords: dict[str, str]):
    # RLS policy DDL needs ACCESS EXCLUSIVE locks. Take every required lock before
    # CREATE ROLE writes the system catalogs, otherwise autovacuum can deadlock
    # while it waits on this transaction and this transaction waits on its table.
    _lock_policy_tables(conn)
    for role in (READER, WORKER):
        if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
            raise ValueError('Application roles already exist; refuse implicit credential rotation')
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE '
                             'NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 12 PASSWORD {}')
                     .format(sql.Identifier(role), sql.Literal(passwords[role])))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout='60s'").format(sql.Identifier(role)))
        conn.execute(sql.SQL("ALTER ROLE {} SET lock_timeout='5s'").format(sql.Identifier(role)))
    conn.execute(sql.SQL('ALTER ROLE {} SET default_transaction_read_only=on').format(sql.Identifier(READER)))
    conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout='5s'").format(sql.Identifier(READER)))
    apply_access(conn)


def role_url(owner_url: str, role: str, password: str) -> str:
    url = make_url(owner_url)
    username = role
    if url.host and url.host.endswith('.pooler.supabase.com'):
        if not url.username or '.' not in url.username:
            raise ValueError('Supabase shared pooler requires the exact project-qualified username')
        username += '.' + url.username.split('.', 1)[1]
    return url.set(username=username, password=password).render_as_string(hide_password=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-file', type=Path, default=Path('.local/secrets/hosted-database.json'))
    args = parser.parse_args()
    try:
        if args.credentials_file.exists():
            raise ValueError('Credential file already exists; refuse to overwrite it')
        args.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        passwords = {role: secrets.token_urlsafe(36) for role in (READER, WORKER)}
        credentials = {role: dict(password=password, database_url=role_url(settings.database_url, role, password),
            database_url_async=role_url(settings.database_url_async, role, password)) for role, password in passwords.items()}
        # Write exclusively before provisioning so credentials survive interruption.
        with args.credentials_file.open('x', encoding='utf-8') as handle:
            json.dump(credentials, handle, indent=2)
        with psycopg.connect(settings.database_url.replace('postgresql+psycopg://','postgresql://'), connect_timeout=15) as conn:
            provision_roles(conn, passwords)
        print('Restricted database roles created. Credentials saved locally; no owner credential exported.')
    except Exception as exc:
        raise SystemExit(f'Role provisioning failed ({type(exc).__name__}); inspect local setup state before retrying.') from None


if __name__ == '__main__':
    main()
