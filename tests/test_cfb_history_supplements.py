import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from sportsbet.ingestion.cfb_final_evidence import digest
from sportsbet.ingestion.provenance import stat_row_sha256
from sportsbet.quant.cfb_history_supplements import plan_supplements, apply_bundle, canonical, POLICY
from tests.test_cfb_final_evidence import bundle, NOW
from tests.test_cfb_history_completeness import primary


def test_supplement_preserves_primary_and_commits_effective_full_row():
    row = primary(); original = deepcopy(row); raw = json.dumps(bundle())
    plan = plan_supplements(raw, [row], now=NOW)
    item, = plan['updates']
    assert row == original
    assert item['receiving_yards'] == item['receptions'] == 0
    assert item['primary_row']['rushing_yards'] == 68
    effective = row | dict(receiving_yards=0, receptions=0)
    assert item['effective_record_sha256'] == stat_row_sha256('cfb', effective)
    assert item['source_sha256'] == digest(canonical(item['manifest']))
    assert item['manifest']['policy_version'] == POLICY
    assert item['bundle_sha256'] == digest(raw)
    replay = plan_supplements(raw, [row], [item], now=NOW)
    assert replay['updates'] == [] and replay['retained'] == 1


def test_only_missing_field_is_supplemented():
    item, = plan_supplements(json.dumps(bundle()), [primary(receiving_yards=0)], now=NOW)['updates']
    assert item['manifest']['supplemented_fields'] == {'receptions': 0}


@pytest.mark.parametrize('updates', [dict(rushing_yards=99), dict(receiving_yards=1), dict(team_id=77)])
def test_conflicting_primary_statistics_or_identity_reject_plan(updates):
    with pytest.raises(ValueError, match='Every requested game'):
        plan_supplements(json.dumps(bundle()), [primary(**updates)], now=NOW)


def test_changed_receipt_cannot_overwrite_retained_supplement():
    raw = json.dumps(bundle()); row = primary(); prior = plan_supplements(raw,[row],now=NOW)['updates']
    b = bundle(); b['sources'][1]['observed_at'] = '2026-09-28T00:02:00Z'
    with pytest.raises(ValueError,match='Existing supplement differs'):
        plan_supplements(json.dumps(b),[row],prior,now=NOW)


def test_missing_primary_or_invalid_hash_cannot_create_history():
    with pytest.raises(ValueError):plan_supplements(json.dumps(bundle()),[],now=NOW)
    row = primary();row['source_record_sha256']='0'*64
    with pytest.raises(ValueError):plan_supplements(json.dumps(bundle()),[row],now=NOW)


def test_empty_or_unreviewed_application_fails_before_database_access():
    db = Mock()
    with pytest.raises(ValueError,match='Positive reviewed count'):
        apply_bundle(db,json.dumps(bundle()),expected_count=0,expected_plan_sha256='x',now=NOW)
    db.execute.assert_not_called()
