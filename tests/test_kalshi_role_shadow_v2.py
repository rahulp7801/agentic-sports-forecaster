"""Future NFL source releases are pinned without rewriting the first freeze."""
import copy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import kalshi_role_shadow_v2 as v2


STAGED = "2026-10-03T09:14:00+00:00"
CAPTURE = datetime(2026, 10, 3, 9, 15, tzinfo=timezone.utc)


def manifest():
    assets, responses = {}, {}
    for kind in v2.KINDS:
        listing = []
        for year in v2.YEARS:
            name = v2.filename(kind, year)
            sha = hashlib.sha256(name.encode()).hexdigest()
            item = dict(id=year, name=name, size=123,
                        updated_at="2026-10-03T09:04:00+00:00", digest="sha256:"+sha)
            listing.append(item)
            assets[f"{kind}_{year}"] = dict(asset_id=year, filename=name,
                size=123, updated_at=item["updated_at"], sha256=sha,
                url=v2.asset_url(kind, year))
        raw = json.dumps(dict(assets=listing))
        responses[kind] = dict(text=raw, sha256=hashlib.sha256(raw.encode()).hexdigest())
    return dict(protocol=v2.MANIFEST_VERSION, staged_at=STAGED,
                assets=assets, release_responses=responses)


def test_exact_official_asset_metadata_must_precede_quote_capture():
    source = manifest()
    assert len(v2.validate_manifest(source, CAPTURE)) == 6
    with pytest.raises(ValueError, match="chronology"):
        v2.validate_manifest(source, datetime(2026, 10, 3, 9, 13, tzinfo=timezone.utc))
    changed = copy.deepcopy(source)
    changed["assets"]["stats_2026"]["sha256"] = "0"*64
    with pytest.raises(ValueError, match="asset chronology or hash"):
        v2.validate_manifest(changed, CAPTURE)
    changed = copy.deepcopy(source)
    changed["release_responses"]["stats"]["text"] += " "
    with pytest.raises(ValueError, match="metadata integrity"):
        v2.validate_manifest(changed, CAPTURE)
