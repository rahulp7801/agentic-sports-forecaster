"""The standalone NBA refresh must preserve existing stats on bad source data."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

import ingest_stats_2025 as script


def _source(ids=(101, 102)):
    return pd.DataFrame({
        "PLAYER_ID": list(ids),
        "PLAYER_NAME": ["Alpha", "Beta"],
        "TEAM_ID": [1, 2],
        "GP": [3, 4],
        "PTS": [40, 50],
    })


def _provider(monkeypatch, frame):
    response = MagicMock()
    response.get_data_frames.return_value = [frame]
    endpoint = MagicMock(return_value=response)
    monkeypatch.setattr(script, "LeagueDashPlayerStats", endpoint)
    return endpoint


def test_valid_refresh_upserts_inside_one_transaction(monkeypatch):
    endpoint = _provider(monkeypatch, _source())
    engine = MagicMock()
    written = []

    def capture(self, table, connection, **kwargs):
        written.append((self.copy(), table, connection, kwargs))

    monkeypatch.setattr(pd.DataFrame, "to_sql", capture)
    assert script.ingest_stats_2025(engine) == 2

    assert endpoint.call_args.kwargs["season"] == "2025-26"
    assert len(written) == 1
    frame, table, connection, kwargs = written[0]
    assert table == "nba_player_stats"
    assert frame["season"].tolist() == [2025, 2025]
    assert connection is engine.begin.return_value.__enter__.return_value
    assert kwargs["if_exists"] == "append"
    assert callable(kwargs["method"])
    engine.begin.assert_called_once()
    connection.execute.assert_not_called()


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(columns=["PLAYER_ID", "PLAYER_NAME"]),
        pd.DataFrame({"PLAYER_ID": [101], "GP": [3]}),
        _source((101, 101)),
        _source((None, 102)),
    ],
    ids=["empty", "missing-name", "duplicate-id", "null-id"],
)
def test_invalid_source_never_opens_a_write_transaction(monkeypatch, frame):
    _provider(monkeypatch, frame)
    engine = MagicMock()
    with pytest.raises(ValueError):
        script.ingest_stats_2025(engine)
    engine.begin.assert_not_called()


def test_insert_failure_propagates_and_transaction_can_roll_back(monkeypatch):
    _provider(monkeypatch, _source())
    engine = MagicMock()

    def fail(*args, **kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(pd.DataFrame, "to_sql", fail)
    with pytest.raises(RuntimeError, match="database write failed"):
        script.ingest_stats_2025(engine)
    engine.begin.return_value.__exit__.assert_called_once()
    assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError