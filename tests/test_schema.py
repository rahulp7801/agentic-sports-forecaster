"""Schema tests (DATA-01, DATA-03).

Tests verify that all required composite indexes exist on play_by_play,
that the query planner uses an Index Scan (not Seq Scan) when seqscan is
disabled, and that odds_snapshots accepts writes and returns snapped_at.

All tests use the pg_engine fixture which skips if DB is not reachable.
"""

from __future__ import annotations

import sqlalchemy as sa
import pytest
import uuid
import json
from copy import deepcopy


def test_pbp_indexes(pg_engine: sa.Engine) -> None:
    """play_by_play must have all 6 required composite indexes (DATA-01).

    Queries pg_indexes system catalog directly so the test is immune to
    SQLAlchemy inspection quirks.
    """
    with pg_engine.connect() as conn:
        result = conn.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'play_by_play'")
        )
        index_names = {row[0] for row in result}

    required = {
        "idx_pbp_season_week",
        "idx_pbp_posteam_season",
        "idx_pbp_defteam_season",
        "idx_pbp_play_type_season",
        "idx_pbp_passer_season",
        "idx_pbp_receiver_season",
    }
    assert required.issubset(index_names), (
        f"Missing indexes on play_by_play: {required - index_names}"
    )


def test_explain_no_seq_scan(pg_engine: sa.Engine) -> None:
    """EXPLAIN on season/posteam/play_type filter must not use Seq Scan (DATA-01).

    Uses SET enable_seqscan = off so the planner is forced to prefer index
    scans regardless of table row count. This is reliable at any data volume —
    including an empty table (avoids the single-row planner heuristic that
    would otherwise choose Seq Scan on small tables).
    """
    with pg_engine.connect() as conn:
        conn.execute(sa.text("SET enable_seqscan = off"))
        plan = conn.execute(
            sa.text(
                "EXPLAIN SELECT * FROM play_by_play "
                "WHERE season = 2023 AND posteam = 'KC' AND play_type = 'pass'"
            )
        ).fetchall()
    plan_text = " ".join(str(row) for row in plan)
    assert "Seq Scan" not in plan_text, (
        f"Unexpected Seq Scan with enable_seqscan=off: {plan_text[:200]}"
    )


def test_odds_snapshot_write_read(pg_engine: sa.Engine) -> None:
    """odds_snapshots must accept a row and return it with auto-populated snapped_at (DATA-03)."""
    with pg_engine.begin() as conn:
        # Insert parent row to satisfy FK (ON CONFLICT DO NOTHING handles reruns)
        conn.execute(
            sa.text(
                "INSERT INTO games (game_id, season, week, home_team, away_team, game_date) "
                "VALUES ('2023_01_KC_DET', 2023, 1, 'KC', 'DET', '2023-09-10') "
                "ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO odds_snapshots (game_id, sportsbook, market_type, line, price) "
                "VALUES ('2023_01_KC_DET', 'DraftKings', 'moneyline', NULL, -150)"
            )
        )
        row = conn.execute(
            sa.text(
                "SELECT game_id, sportsbook, market_type, price, snapped_at "
                "FROM odds_snapshots "
                "WHERE game_id = '2023_01_KC_DET' "
                "ORDER BY snapped_at DESC LIMIT 1"
            )
        ).fetchone()

    assert row is not None, "No row returned from odds_snapshots after insert"
    assert row[0] == "2023_01_KC_DET", f"game_id mismatch: {row[0]}"
    assert row[1] == "DraftKings", f"sportsbook mismatch: {row[1]}"
    assert row[2] == "moneyline", f"market_type mismatch: {row[2]}"
    assert row[3] == -150, f"price mismatch: {row[3]}"
    assert row[4] is not None, "snapped_at is None — server_default not applied"


def test_dashboard_snapshot_batch_commits_together_and_rolls_back_second_row_failure(
        pg_engine: sa.Engine, monkeypatch) -> None:
    """The real executemany transaction cannot leave one of two outputs updated."""
    from sportsbet import dashboard
    prefix = 'snapshot-batch-test:' + uuid.uuid4().hex
    first, second = prefix + ':first', prefix + ':second'
    captured = '2026-10-18T18:53:07.610862+00:00'
    payloads = [(first, {'captured_at': captured, 'label': 'café', 'nested': {'valid': True}}),
                (second, {'captured_at': captured, 'execution_ready': False})]
    original = deepcopy(payloads)
    parameters = {'first': first, 'second': second}
    try:
        with pg_engine.begin() as conn:
            conn.execute(sa.text('''INSERT INTO dashboard_snapshots(snapshot_key,payload,updated_at)
                VALUES (:key,CAST(:payload AS JSONB),'2026-01-01T00:00:00Z')'''),
                [{'key': first, 'payload': json.dumps({'old': 1})},
                 {'key': second, 'payload': json.dumps({'old': 2})}])
        def factory():
            return sa.create_engine(pg_engine.url, connect_args={'connect_timeout': 3})
        monkeypatch.setattr(dashboard, 'get_sync_engine', factory)
        def read():
            with pg_engine.connect() as conn:
                return conn.execute(sa.text('''SELECT snapshot_key,payload,updated_at
                    FROM dashboard_snapshots WHERE snapshot_key IN (:first,:second)
                    ORDER BY snapshot_key'''), parameters).all()
        before = read()

        # JSON serialization succeeds; PostgreSQL JSONB rejects U+0000 only
        # after the first row's update, proving real transaction rollback.
        with pytest.raises(sa.exc.DBAPIError) as raised:
            dashboard.publish_snapshots([payloads[0], (second, {'value': '\x00'})])
        assert raised.value.orig.sqlstate == '22P05'
        assert read() == before

        dashboard.publish_snapshots(payloads)
        committed = read()
        assert [(row[0], row[1]) for row in committed] == payloads
        assert committed[0][2] == committed[1][2]
        assert committed[0][2] != before[0][2]
        assert payloads == original
    finally:
        with pg_engine.begin() as conn:
            conn.execute(sa.text('DELETE FROM dashboard_snapshots WHERE snapshot_key IN (:first,:second)'), parameters)


def test_publication_receipt_projection_preserves_real_jsonb_types_and_exact_clock(
        pg_engine: sa.Engine) -> None:
    """Read only the receipt scalar through psycopg without normalizing its value."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        'postgres_receipt_verifier', Path('.github/scripts/verify-published-snapshots.py'))
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    captured = '2026-10-19T15:02:27.893939+00:00'
    equivalent_clock = '2026-10-19T15:02:27.893939Z'
    fixtures = [
        ('exact', {'captured_at': captured, 'unrelated': 'x' * (256 * 1024)}, captured),
        ('equivalent', {'captured_at': equivalent_clock}, equivalent_clock),
        ('null', {'captured_at': None}, None),
        ('missing-field', {'unrelated': captured}, None),
        ('number-field', {'captured_at': 1792422147}, 1792422147),
        ('bool-field', {'captured_at': True}, True),
        ('list-field', {'captured_at': [captured]}, [captured]),
        ('object-field', {'captured_at': {'clock': captured}}, {'clock': captured}),
        ('array-payload', [{'captured_at': captured}], None),
        ('string-payload', captured, None),
        ('number-payload', 1792422147, None),
        ('bool-payload', True, None),
        ('null-payload', None, None),
    ]
    prefix = 'receipt-projection-test:' + uuid.uuid4().hex + ':'
    rows = [{'key': prefix + name, 'payload': json.dumps(payload, allow_nan=False)}
            for name, payload, _ in fixtures]
    missing_key = prefix + 'missing-row'
    report = {'markets': {'nfl': {'captured_at': captured}}}
    try:
        with pg_engine.begin() as conn:
            conn.execute(sa.text('''INSERT INTO dashboard_snapshots(snapshot_key,payload)
                VALUES (:key,CAST(:payload AS JSONB))'''), rows)
            # This is the real psycopg connection: %s parameters and JSONB scalar
            # decoding match the hosted receipt verifier's driver path.
            driver = conn.connection.driver_connection
            for name, _, expected in fixtures:
                key = prefix + name
                projected = verifier.read_capture(driver, key)
                assert projected == {'captured_at': expected}
                assert type(projected['captured_at']) is type(expected)
                assert set(projected) == {'captured_at'}

                def read(receipt_key):
                    assert receipt_key == 'markets:nfl'
                    return verifier.read_capture(driver, key)

                if name == 'exact':
                    assert verifier.verify_captures(report, read) == 1
                    # Even equivalent ISO spellings must retain the original
                    # capture string; neither side may substitute a new clock.
                    different_report = {'markets': {'nfl': {'captured_at': equivalent_clock}}}
                    with pytest.raises(ValueError, match='does not match this run'):
                        verifier.verify_captures(different_report, read)
                else:
                    with pytest.raises(ValueError, match='does not match this run'):
                        verifier.verify_captures(report, read)

            assert verifier.read_capture(driver, missing_key) is None
            with pytest.raises(ValueError, match='does not match this run'):
                verifier.verify_captures(report, lambda _: verifier.read_capture(driver, missing_key))
    finally:
        with pg_engine.begin() as conn:
            conn.execute(sa.text('DELETE FROM dashboard_snapshots WHERE snapshot_key=:key'),
                         [{'key': row['key']} for row in rows])
