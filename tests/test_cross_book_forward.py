from datetime import datetime,timedelta,timezone

import pytest
from sportsbet.quant import cross_book_forward as forward
from sportsbet.quant import market_challengers as challenger
from tests.test_history_shadow import fixture

CUT=datetime(2026,9,30,tzinfo=timezone.utc)


def row(at=CUT):
    payload,_,_=fixture(now=at)
    return payload | dict(prediction_id='forward-test',
        model_version=forward.PROTOCOL['model_versions']['nfl'],
        history_observed_before=at.isoformat(),
        history_policy_version=forward.PROTOCOL['history_policies']['nfl'],
        recommendation_policy_version=forward.PROTOCOL['recommendation_policy_version'])


def test_forward_rejects_changed_evaluator(monkeypatch):
    monkeypatch.setattr(forward,'FROZEN_DIGESTS',{})
    with pytest.raises(ValueError,match='dependencies changed'):forward.evaluate([],'nfl')


def test_prefreeze_archive_never_enters_confirmation():
    report=forward.evaluate([row(CUT-timedelta(days=1))],'nfl',now=CUT-timedelta(hours=1))
    assert report['recorded_rows']==0
    assert report['status']=='awaiting_start'
    assert report['promote'] is False


def test_new_capture_cannot_reuse_prefreeze_quote():
    report=forward.evaluate([row()],'nfl',now=CUT+timedelta(minutes=1))
    assert report['recorded_rows']==0  # fixture quote was ten seconds before freeze


def test_forward_accepts_genuine_new_quote_and_keeps_pending():
    report=forward.evaluate([row(CUT+timedelta(minutes=1))],'nfl',now=CUT+timedelta(minutes=2))
    assert report['eligible_rows']==1
    assert report['selected']==0
    assert report['status']=='insufficient_evidence'


@pytest.mark.parametrize('key,value',[
    ('history_policy_version','changed'),('recommendation_policy_version','changed')])
def test_forward_fails_closed_on_policy_change(key,value):
    value_row=row(CUT+timedelta(minutes=1));value_row[key]=value
    with pytest.raises(ValueError,match='policy'):forward.evaluate([value_row],'nfl',now=CUT+timedelta(minutes=2))


def test_future_capture_rejected():
    with pytest.raises(ValueError,match='Future capture'):
        forward.evaluate([row(CUT+timedelta(days=1))],'nfl',now=CUT)


def test_forward_keeps_sports_and_model_versions_separate():
    value=row(CUT+timedelta(minutes=1));value['model_version']='empirical-jeffreys-v4'
    assert forward.evaluate([value],'nfl',now=CUT+timedelta(minutes=2))['recorded_rows']==0
    assert forward.evaluate([row(CUT+timedelta(minutes=1))],'cfb',now=CUT+timedelta(minutes=2))['recorded_rows']==0


def test_selection_manifest_pending_and_future_settlement(monkeypatch):
    from tests.test_market_challengers import item
    target=item(entry=CUT+timedelta(minutes=1))
    target['row'].update(quote_source_sha256='source')
    reference=item(book='b',odds=-1000,entry=CUT+timedelta(minutes=1))
    # Both authenticated outcomes arrived later than the as-of time.
    monkeypatch.setattr(challenger,'observations',lambda *_:([target,reference],{}))
    report=forward.evaluate([],'nfl',now=CUT+timedelta(minutes=2))
    assert report['selected']==1
    assert report['decided']==0 and report['pending']==1
    assert report['flat_stake_roi'] is None
    assert report['selections'][0]['verified_outcome'] is None
    assert report['selections'][0]['reference_prediction_ids']==[reference['row']['prediction_id']]
    assert report['promote'] is False


def test_sufficient_positive_evidence_still_requires_review(monkeypatch):
    from tests.test_market_challengers import item
    values=[]
    for game in range(50):
        for player in range(2):
            values.extend([item(game=str(game),player=str(player),entry=CUT+timedelta(minutes=1)),
                item(game=str(game),player=str(player),book='b',odds=-1000,entry=CUT+timedelta(minutes=1),q=.7)])
    monkeypatch.setattr(challenger,'observations',lambda *_:(values,{}))
    report=forward.evaluate([],'nfl',now=CUT+timedelta(days=1))
    assert report['decided']==100 and report['settled_games']==50
    assert report['status']=='review_required'
    assert report['promote'] is False


def test_hosted_source_filters_before_fetching_old_payloads(monkeypatch):
    from contextlib import contextmanager
    calls=[]
    class Cursor:
        def fetchall(self):return []
    class Connection:
        def execute(self,query,params):
            calls.append((query,params));return Cursor()
    @contextmanager
    def connection():yield Connection()
    ledger=forward.ProspectiveLedger(database_url='postgresql://localhost/unused')
    monkeypatch.setattr(ledger,'connect',connection)
    assert ledger._prediction_records(ordered=True)==[]
    query,params=calls[0]
    assert 'WHERE CASE WHEN' in query and '::timestamptz>=?::timestamptz' in query
    assert query.endswith('ORDER BY id')
    assert params==(list(forward.PROTOCOL['model_versions']),
        list(forward.PROTOCOL['model_versions'].values()),forward.PROTOCOL['captured_after'])
