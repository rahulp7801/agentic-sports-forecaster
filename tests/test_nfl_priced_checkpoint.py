"""Private retention must preserve the existing prospective edge assessment."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from sportsbet.quant import nfl_priced_checkpoint as checkpoint


def audit_inputs():
    shared = dict(sport='nfl', model_version='empirical-jeffreys-v4',
                  captured_after='2026-09-23T00:34:15+00:00')
    return {
        'All forecasts': dict(**shared, cohort='all_predictions',
                              prospective={'paired_games': 2}),
        'Recommendations': dict(**shared, cohort='recommendations',
                                prospective={'decided': 1, 'settled_games': 1}),
    }


def test_priced_checkpoint_retains_frozen_assessment_and_no_promotion():
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    report = checkpoint.build_report(audit_inputs(), observed_at=now)
    assert report['assessment']['status'] == 'insufficient_data'
    assert report['assessment']['counts'] == {
        'paired_games': 2, 'decided_recommendations': 1, 'recommendation_games': 1}
    assert report['promote'] is False and report['target_verified'] is False
    assert set(report['cohorts']) == {'all_forecasts', 'recommendations'}
    observed, payload, digest = checkpoint.encode_report(report)
    assert observed == now
    assert digest == hashlib.sha256(payload.encode()).hexdigest()
    assert json.loads(payload)['protocol']['version'] == checkpoint.PROTOCOL['version']


@pytest.mark.parametrize('change', [
    ('All forecasts', 'model_version', 'new-model'),
    ('Recommendations', 'captured_after', '2026-10-01T00:00:00+00:00'),
    ('Recommendations', 'cohort', 'all_predictions'),
])
def test_priced_checkpoint_rejects_changed_source_contract(change):
    reports = audit_inputs()
    reports[change[0]][change[1]] = change[2]
    with pytest.raises(ValueError):
        checkpoint.build_report(reports)


def test_priced_checkpoint_rejects_promotion_nonfinite_and_naive_time():
    report = checkpoint.build_report(audit_inputs())
    report['promote'] = True
    with pytest.raises(ValueError, match='contract'):
        checkpoint.encode_report(report)
    report['promote'] = False
    report['cohorts']['all_forecasts']['bad'] = float('nan')
    with pytest.raises(ValueError):
        checkpoint.encode_report(report)
    with pytest.raises(ValueError, match='timezone'):
        checkpoint.build_report(audit_inputs(), observed_at=datetime(2026, 10, 2))
