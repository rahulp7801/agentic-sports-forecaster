from datetime import datetime, timedelta, timezone

import pytest

from sportsbet.ingestion.prop_odds import parse_event_quotes
from sportsbet.quant import cross_book_receipt_forward as forward
from sportsbet.quant.cross_book_quote_receipt import capture, verified_references
from sportsbet.quant.market_baseline import paired_market_baseline
from tests.test_history_shadow import fixture


NOW = datetime(2026, 10, 3, 1, tzinfo=timezone.utc)


def evidence():
    payload, _, event = fixture('nfl', 'receptions', now=NOW)
    event['bookmakers'][0]['markets'][0]['outcomes'][0]['price'] = 120
    event['bookmakers'][0]['markets'][0]['outcomes'][1]['price'] = -140
    other = dict(key='other', last_update=(NOW-timedelta(seconds=10)).isoformat(),
        markets=[dict(key='player_receptions',
            last_update=(NOW-timedelta(seconds=10)).isoformat(), outcomes=[
                dict(name='Over',description='Player',point=payload['line'],price=-130),
                dict(name='Under',description='Player',point=payload['line'],price=100)])])
    event['bookmakers'].append(other)
    quotes = parse_event_quotes(event, 'nfl')
    offer = next(q for q in quotes if q.sportsbook == 'book' and q.side == 'Over')
    payload.update(american_odds=offer.price,
        quote_source_sha256=offer.source_sha256,
        quote_source_record_sha256=offer.source_record_sha256,
        model_version='empirical-jeffreys-v4-nfl-history-v1',
        history_policy_version='nfl-explicit-receiving-v1',
        history_observed_before=NOW.isoformat(),
        recommendation_policy_version='confidence-floor-v2',
        prediction_id='receipt-test',
        **paired_market_baseline(offer, quotes))
    payload['cross_book_quote_receipt'] = capture(offer, quotes)
    return payload, offer, quotes


def test_receipt_uses_existing_source_and_rejects_tampering():
    row, offer, quotes = evidence()
    refs = verified_references(row, decision_at=NOW)
    assert refs == pytest.approx({'other': 0.5306122448979592})
    assert len(row['cross_book_quote_receipt']['references']) == 1
    assert capture(offer, quotes+[quotes[-1]])['references'] == []
    changed = dict(row, cross_book_quote_receipt={
        **row['cross_book_quote_receipt'],
        'references': [dict(row['cross_book_quote_receipt']['references'][0],over_odds=-120)]})
    assert verified_references(changed, decision_at=NOW) is None
    assert verified_references(row, decision_at=NOW+timedelta(seconds=301)) == {}


def test_forward_uses_one_committed_offer_and_keeps_it_pending():
    row, _, _ = evidence()
    report = forward.evaluate([row], 'nfl', now=NOW+timedelta(minutes=1))
    assert report['recorded_rows'] == report['eligible_rows'] == 1
    assert report['coverage']['comparable_offers'] == 1
    assert report['selected'] == report['pending'] == 1
    assert report['decided'] == 0 and report['promote'] is False
    assert report['selections'][0]['reference_books'] == ['other']


def test_forward_does_not_retrofit_prefreeze_rows_or_future_results():
    row, _, _ = evidence()
    assert forward.evaluate([dict(row, captured_at='2026-10-02T07:59:59+00:00')],
        'nfl', now=NOW)['recorded_rows'] == 0
    bad = dict(row, cross_book_quote_receipt={**row['cross_book_quote_receipt'],
        'references': [dict(row['cross_book_quote_receipt']['references'][0],
            under_record_sha256='0'*64)]})
    report = forward.evaluate([bad], 'nfl', now=NOW+timedelta(minutes=1))
    assert report['selected'] == 0
    assert report['coverage']['missing_or_invalid_receipt'] == 1


def test_forward_compares_full_response_before_selecting_strongest(monkeypatch):
    from sportsbet.quant import market_challengers as challenger
    from tests.test_market_challengers import item

    first = item(entry=NOW, odds=120, source='one-response', y=None)
    stronger = item(entry=NOW+timedelta(seconds=2), odds=140, line=3.5,
        source='one-response', y=None)
    monkeypatch.setattr(challenger, 'observations', lambda *_:([first,stronger],{}))
    monkeypatch.setattr(forward, 'verified_references',
        lambda row, *, decision_at:{'other':.6})
    report = forward.evaluate([], 'nfl', now=NOW+timedelta(minutes=1))
    assert report['selected'] == 1
    assert report['selections'][0]['american_odds'] == 140
    assert report['selections'][0]['decision_at'] == stronger['entry'].isoformat()
