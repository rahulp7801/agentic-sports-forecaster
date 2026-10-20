"""Pandas SQL writer for repeatable stat refreshes and provider corrections."""
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import MetaData, Table, and_, case

def upsert_rows(keys: list[str], *, preserve_observation_on_unchanged: bool = False,
                skip_unchanged_updates: bool = False):
    if skip_unchanged_updates and not preserve_observation_on_unchanged:
        raise ValueError('Skipping unchanged updates requires observation preservation')
    target = None

    def write(table, conn, columns, data_iter):
        nonlocal target
        rows = [dict(zip(columns, row)) for row in data_iter]
        if not rows:
            return 0
        # Pandas infers VARCHAR for an all-null numeric column, even when
        # appending to an existing INTEGER column. Bind using the actual
        # database schema; one reflection serves all chunks in this writer.
        if target is None:
            target = Table(table.name, MetaData(), schema=table.table.schema,
                autoload_with=conn)
        stmt = insert(target).values(rows)
        updates={name:stmt.excluded[name] for name in columns if name not in keys}
        if preserve_observation_on_unchanged:
            if not {'source_observed_at','source_record_sha256','source_provider','source_sha256'} <= set(columns):
                raise ValueError('Complete source provenance columns are required')
            # A repeat pull of the same normalized row is not a new observation.
            # A correction to *any* supplied data field resets the observation
            # time and source bundle, including fields outside the core hash.
            bundle_fields={'source_sha256','source_player_sha256','source_schedule_sha256'}
            stable_fields=[name for name in columns if name not in keys
                and name not in bundle_fields|{'source_observed_at'}]
            unchanged=and_(target.c.source_observed_at.is_not(None),
                *(target.c[name].is_not_distinct_from(stmt.excluded[name]) for name in stable_fields))
            for name in columns:
                if name in bundle_fields:
                    updates[name]=case((unchanged,target.c[name]),else_=stmt.excluded[name])
            updates['source_observed_at']=case(
                (unchanged,target.c.source_observed_at),else_=stmt.excluded.source_observed_at)
        # The preserve predicate already makes every effective value identical.
        # Opted-in source writers can avoid UPDATE/trigger work for that replay;
        # conflicting tuples may still be locked by PostgreSQL.
        stmt = stmt.on_conflict_do_update(index_elements=keys,set_=updates,
            where=~unchanged if skip_unchanged_updates else None)
        return conn.execute(stmt).rowcount
    return write
