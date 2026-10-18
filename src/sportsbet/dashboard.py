"""Publish sanitized result snapshots for the hosted dashboard."""
import json
from sqlalchemy import text
from sportsbet.db.connection import get_sync_engine

MAX_SNAPSHOT_BATCH_SIZE = 16

def load_snapshot(key: str) -> dict | None:
    engine = get_sync_engine()
    try:
        with engine.connect() as conn:
            return conn.execute(text('SELECT payload FROM dashboard_snapshots WHERE snapshot_key=:key'),
                {'key':key}).scalar_one_or_none()
    finally:
        engine.dispose()

def publish_snapshot(key: str, payload: dict) -> None:
    engine = get_sync_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO dashboard_snapshots(snapshot_key,payload) VALUES (:key,CAST(:payload AS JSONB)) '
                'ON CONFLICT(snapshot_key) DO UPDATE SET payload=excluded.payload,updated_at=NOW()'),
                {'key':key,'payload':json.dumps(payload,allow_nan=False)})
    finally:
        engine.dispose()


def publish_snapshots(snapshots: list[tuple[str, dict]] | tuple[tuple[str, dict], ...]) -> None:
    """Publish a bounded explicit group atomically, after serializing every row."""
    if type(snapshots) not in (list, tuple):
        raise ValueError('Invalid snapshot batch')
    items = tuple(snapshots)
    if not 1 <= len(items) <= MAX_SNAPSHOT_BATCH_SIZE:
        raise ValueError('Invalid snapshot batch')
    rows = []
    keys = set()
    for item in items:
        if type(item) not in (list, tuple) or len(item) != 2:
            raise ValueError('Invalid snapshot batch')
        key, payload = item
        if (type(key) is not str or not key or '\x00' in key
                or key in keys or type(payload) is not dict):
            raise ValueError('Invalid snapshot batch')
        keys.add(key)
        rows.append({'key': key, 'payload': json.dumps(payload, allow_nan=False)})
    engine = get_sync_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO dashboard_snapshots(snapshot_key,payload) VALUES (:key,CAST(:payload AS JSONB)) '
                'ON CONFLICT(snapshot_key) DO UPDATE SET payload=excluded.payload,updated_at=NOW()'), rows)
    finally:
        engine.dispose()
