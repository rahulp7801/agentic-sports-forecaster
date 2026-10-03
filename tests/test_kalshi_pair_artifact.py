"""The private artifact retains the exact raw market and source receipts."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import zipfile

import pytest

from sportsbet.quant import kalshi_pair_artifact as artifact
from sportsbet.quant import kalshi_role_shadow_v2 as v2
from sportsbet.quant.kalshi_market_cohort import freeze
from tests.test_kalshi_role_shadow import fixture
from tests.test_kalshi_role_shadow_v2 import manifest


NOW = datetime(2026, 10, 2, 18, 46, tzinfo=timezone.utc)


def setup(tmp_path, monkeypatch):
    archive, _, stats, snaps, identity = fixture()
    source = manifest()
    monkeypatch.setattr(v2, "load_sources", lambda *args:(stats, snaps))
    monkeypatch.setattr(v2.v1, "identity_index", lambda *args:identity)
    cohort = freeze(archive, NOW.isoformat())
    shadow = v2.build_report(archive, cohort, tmp_path, source, now=NOW)
    pair = dict(protocol="kalshi-nfl-contemporaneous-pair-v1",
        started_at=NOW.isoformat(), completed_at=(NOW+timedelta(seconds=2)).isoformat(),
        market_selection_sha256=cohort["selection_sha256"],
        forecasts_sha256=shadow["forecasts_sha256"], selected_contracts=1,
        forecast_contracts=1, cohort=cohort, shadow=shadow)
    pair_path=tmp_path/'pair.json'
    pair_path.write_text(json.dumps(pair),encoding='utf-8')
    source_dir=tmp_path/'sources'
    source_dir.mkdir()
    (source_dir/'source-manifest.json').write_text(json.dumps(source),encoding='utf-8')
    for item in source['assets'].values():
        (source_dir/item['filename']).write_bytes(b'bounded fixture source')
    market_dir=tmp_path/'markets'
    market_dir.mkdir()
    (market_dir/'market.json').write_text(json.dumps(archive),encoding='utf-8')
    return pair_path,source_dir,market_dir


def test_private_pack_replays_and_retains_raw_inputs(tmp_path,monkeypatch):
    pair_path,source_dir,market_dir=setup(tmp_path,monkeypatch)
    output=tmp_path/'private.zip'
    summary=artifact.pack(pair_path,source_dir,market_dir,output)
    assert summary['files']==11
    with zipfile.ZipFile(output) as packed:
        names=set(packed.namelist())
        assert 'market-archive.json' in names and 'pair.json' in names
        assert len([name for name in names if name.endswith('.parquet')])==6
        assert 'manifest.json' in names
    with pytest.raises(FileExistsError):
        artifact.pack(pair_path,source_dir,market_dir,output)


def test_private_pack_rejects_missing_matching_archive(tmp_path,monkeypatch):
    pair_path,source_dir,market_dir=setup(tmp_path,monkeypatch)
    (market_dir/'market.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match="no unique"):
        artifact.pack(pair_path,source_dir,market_dir,tmp_path/'private.zip')
