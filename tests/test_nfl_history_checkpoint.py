"""The live NFL history-model checkpoint must not mix with the retired cohort."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import nfl_history_checkpoint as checkpoint
from sportsbet.quant import nfl_history_edge


def frozen_result():
    protocol = dict(nfl_history_edge.PROTOCOL)
    return {
        'protocol': protocol,
        'protocol_sha256': hashlib.sha256(json.dumps(protocol, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest(),
        'evaluator_sha256': nfl_history_edge.source_digests(),
        'sport': 'nfl',
        'observed_at': datetime(2026, 10, 2, tzinfo=timezone.utc).isoformat(),
        'status': 'insufficient_data',
        'assessment': {'status': 'insufficient_data'},
        'cohorts': {'all_predictions': {'paired_games': 0},
                    'recommendations': {'decided': 0}},
        'promote': False,
        'scope': 'Separate sport evidence; hypothetical recorded prices, no executed profit.',
    }


def test_current_model_audit_retains_distinct_protocol_and_no_promotion():
    report = checkpoint.build_report(frozen_result())
    assert report['protocol']['model_version'] == 'empirical-jeffreys-v4-nfl-history-v1'
    assert report['protocol']['version'] == 'nfl-history-priced-prospective-v1'
    assert report['target_verified'] is False
    observed, payload, digest = checkpoint.encode_report(report)
    assert observed == datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert digest == hashlib.sha256(payload.encode()).hexdigest()


@pytest.mark.parametrize('change', [
    {'protocol': {'version': 'nfl-priced-prospective-checkpoint-v1'}},
    {'sport': 'cfb'},
    {'promote': True},
    {'status': 'review_required'},
    {'evaluator_sha256': {}},
    {'raw_predictions': [{'player': 'Must never be stored'}]},
    {'cohorts': {'recommendations': {}}},
    {'observed_at': '2026-09-28T00:00:00+00:00'},
    {'observed_at': '2026-10-02T00:00:00'},
])
def test_current_model_audit_rejects_changed_or_early_contract(change):
    with pytest.raises((ValueError, TypeError)):
        checkpoint.build_report(frozen_result() | change)


def test_current_model_audit_fails_closed_on_changed_evaluator(monkeypatch):
    assert checkpoint.frozen_source_digests() == checkpoint.FROZEN_DIGESTS
    monkeypatch.setattr(checkpoint, 'FROZEN_DIGESTS',
                        checkpoint.FROZEN_DIGESTS | {'runner': '0' * 64})
    with pytest.raises(ValueError, match='new protocol required'):
        checkpoint.build_report(frozen_result())


def test_current_model_audit_rejects_forged_target_and_nonfinite_report():
    report = checkpoint.build_report(frozen_result())
    report['target_verified'] = True
    with pytest.raises(ValueError):
        checkpoint.encode_report(report)
    report['target_verified'] = False
    report['cohorts']['recommendations']['bad'] = float('nan')
    with pytest.raises(ValueError):
        checkpoint.encode_report(report)
