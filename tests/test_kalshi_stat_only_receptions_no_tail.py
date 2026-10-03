from datetime import datetime, timezone
import sys

import pytest

from sportsbet.quant import kalshi_stat_only_receptions_no_tail as tail
from sportsbet.quant.kalshi_market_cohort import digest

GATE = '2026-10-06T06:15:00+00:00'
LATER = datetime(2026, 10, 6, 7, tzinfo=timezone.utc)


def fixture(monkeypatch, *, missing=False):
    rows = [dict(ticker=f'contract-{i}', milestone_id=f'game-{i%6}',
                 model_win_probability='0.8', displayed_ask='0.54') for i in range(8)]
    monkeypatch.setattr(tail.frozen, 'preflight', lambda *args: (
        dict(first_eligible_settlement_at=GATE, original_market_contracts=452,
             model_forecasts=144, paper_candidates=70), {}))
    monkeypatch.setattr(tail, 'selected_rows', lambda *args: rows)
    monkeypatch.setattr(tail, 'unpack', lambda pair: ({}, {}))
    states = {f'other-{i}': ('not_returned', None) for i in range(444)}
    states.update({row['ticker']: ('venue_verified', 'no') for row in rows})
    if missing:
        states[rows[-1]['ticker']] = ('not_returned', None)
    monkeypatch.setattr(tail.venue, 'venue_results', lambda *args, **kwargs:
                        ([None] * 452, states))
    receipt = dict(protocol=tail.capture.VERSION, evidence_sha256='raw-evidence')
    receipt['record_sha256'] = digest(receipt)
    return receipt


@pytest.mark.parametrize('missing', [False, True])
def test_forward_receptions_tail_keeps_full_denominator_and_no_edge(monkeypatch, missing):
    receipt = fixture(monkeypatch, missing=missing)
    report = tail.evaluate({}, {}, {}, {}, {}, None, None, receipt, now=LATER)
    assert report['original_market_contracts'] == 452
    assert report['paper_candidates'] == 8 and report['paper_games'] == 6
    assert report['verified_candidates'] == (7 if missing else 8)
    assert report['result_counts'] == ({'not_returned': 1, 'venue_verified': 7}
                                       if missing else {'venue_verified': 8})
    assert report['full_group_win_rate'] == (None if missing else '1')
    assert report['full_group_gross_unit_profit'] == (None if missing else '3.68')
    assert report['roi'] is None and report['edge_established'] is False
    assert report['qualified_picks'] == 0


def test_forward_receptions_tail_refuses_early_or_tampered_result(monkeypatch):
    receipt = fixture(monkeypatch)
    with pytest.raises(ValueError, match='premature'):
        tail.evaluate({}, {}, {}, {}, {}, None, None, receipt,
                      now=datetime(2026, 10, 6, 6, tzinfo=timezone.utc))
    receipt['evidence_sha256'] = 'tampered'
    with pytest.raises(ValueError, match='integrity'):
        tail.evaluate({}, {}, {}, {}, {}, None, None, receipt, now=LATER)

def test_forward_receptions_tail_rejects_changed_historical_report_before_replay(monkeypatch, tmp_path):
    historical = tmp_path / 'historical.json'
    historical.write_text('changed', encoding='utf-8')
    output = tmp_path / 'forward.json'
    argv = ['diagnostic']
    for name in ('pair', 'market', 'forecast', 'quotes', 'decisions', 'source-dir', 'schedule'):
        argv += ['--' + name, str(tmp_path / name)]
    argv += ['--historical-tail', str(historical), '--output', str(output)]
    monkeypatch.setattr(sys, 'argv', argv)
    with pytest.raises(SystemExit) as error:
        tail.main()
    assert error.value.code == 2
    assert not output.exists()
