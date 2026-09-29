from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from sportsbet.quant import market_challengers as research
from tests.test_history_shadow import fixture

NOW=datetime(2026,9,20,10,tzinfo=timezone.utc)


def payload(side='over', prediction_id='p', **changes):
    row,_,_=fixture(side=side,now=NOW)
    return row | {'prediction_id':prediction_id} | changes


def item(game='game',player='player',book='a',side='over',q=.5,odds=150,
         entry=NOW,quote=None,start=None,source='source',line=2.5,y=1,p=.8):
    return dict(unit=(game,player,'receptions',line),entry=entry,
        quote=quote or entry-timedelta(seconds=30),start=start or entry+timedelta(hours=2),
        p=p,q=q,n=20,y=y,observed=entry+timedelta(hours=4),
        row=dict(prediction_id=game+player+book+side+str(line),sportsbook=book,
            direction=side,american_odds=odds,quote_source_sha256=source))


def test_real_quote_proof_is_required_and_no_network_needed():
    valid=payload()
    observations,_=research.observations([valid],'nfl','empirical-jeffreys-v4')
    assert len(observations)==1
    assert observations[0]['q']==pytest.approx(.5)
    assert observations[0]['y'] is None
    valid['quote_source_record_sha256']='0'*64
    assert research.observations([valid],'nfl','empirical-jeffreys-v4')[0]==[]


def test_unverified_boolean_outcome_is_not_a_training_label():
    row=payload(outcome=True,outcome_observed_at=(NOW+timedelta(days=2)).isoformat())
    observed,_=research.observations([row],'nfl','empirical-jeffreys-v4')
    assert observed[0]['y'] is None
    assert observed[0]['observed'] is None


def without_retained_baseline(row):
    return {k:v for k,v in row.items() if not k.startswith('market_')}


def test_fallback_pair_cannot_use_later_receipt_or_different_response():
    over=without_retained_baseline(payload(prediction_id='over'))
    under=without_retained_baseline(payload('under','under',captured_at=(NOW+timedelta(seconds=1)).isoformat()))
    observed,_=research.observations([over,under],'nfl','empirical-jeffreys-v4')
    assert [x['row']['prediction_id'] for x in observed]==['under']
    # Changing a response hash invalidates its source proof as well as pairing.
    under['quote_source_sha256']='1'*64
    assert research.observations([over,under],'nfl','empirical-jeffreys-v4')[0]==[]


def test_integer_lines_are_outside_fixed_protocol():
    row,_,_=fixture(line=40,now=NOW)
    row['prediction_id']='integer'
    assert research.observations([row],'nfl','empirical-jeffreys-v4')[0]==[]


def training():
    return [item(game=str(i),entry=NOW-timedelta(days=10-i)) for i in range(5)]


def test_fit_only_uses_previous_authenticated_other_games():
    target=item(game='target')
    history=training()
    assert research.fit_residual_weight(history,target)==(1.,5)
    poison=[item(game='target',entry=NOW-timedelta(days=2),y=0),
        item(game='future',entry=NOW+timedelta(days=1),y=0),
        item(game='unsettled',entry=NOW-timedelta(days=1),y=None),
        item(game='late_receipt',entry=NOW-timedelta(days=1),y=0)]
    poison[-1]['observed']=NOW
    assert research.fit_residual_weight(history+poison,target)==(1.,5)
    assert research.fit_residual_weight(history[:4],target)==(None,4)
    for x in history:x['y']=0
    assert research.fit_residual_weight(history,target)==(0.,5)


def test_fit_does_not_overweight_many_lines_for_one_player_game():
    history=training()
    for x in history[:3]:x['y']=0
    expected=research.fit_residual_weight(history,item())
    duplicate=[dict(history[-1],unit=history[-1]['unit'][:3]+(i+.5,)) for i in range(50)]
    assert research.fit_residual_weight(history+duplicate,item())==expected


def test_duplicate_sides_and_books_do_not_multiply_forecast_units():
    first=item(book='a');later=item(book='b',entry=NOW+timedelta(seconds=1))
    assert research.earliest_units([later,first])==[first]


def test_cross_book_excludes_own_probability_and_never_uses_outcomes():
    a=item(book='a',q=.9,odds=110)
    b=item(book='b',q=.4,odds=-1000)
    assert research.cross_book_candidates([a,b])[0]==[]
    a['row']['american_odds']=200
    selected,_=research.cross_book_candidates([a,b])
    assert len(selected)==1
    assert selected[0]['probability']==.4
    assert selected[0]['ev']==pytest.approx(.2)
    a['y']=0;b['y']=None
    again,_=research.cross_book_candidates([a,b])
    assert [(c['x']['row']['prediction_id'],c['ev']) for c in again]==[(c['x']['row']['prediction_id'],c['ev']) for c in selected]


@pytest.mark.parametrize('change',[{'source':'other'}, {'line':3.5},
    {'quote':NOW-timedelta(seconds=301)}, {'start':NOW}])
def test_cross_book_requires_same_batch_line_fresh_pregame_prices(change):
    assert research.cross_book_candidates([item(),item(book='b',odds=-1000,**change)])[0]==[]


def test_cross_book_rejects_conflicting_book_side_prices():
    values=[item(),item(odds=200),item(book='b',odds=-1000)]
    selected,coverage=research.cross_book_candidates(values)
    assert selected==[]
    assert coverage['ambiguous_books']==1


def test_only_one_candidate_per_player_game_and_earliest_batch_wins():
    values=[item(),item(book='b',odds=-1000),
        item(source='later',line=3.5,entry=NOW+timedelta(minutes=10),odds=300),
        item(book='b',source='later',line=3.5,entry=NOW+timedelta(minutes=10),odds=-1000)]
    selected,_=research.cross_book_candidates(values)
    assert len(selected)==1
    assert selected[0]['decision']==NOW
    assert selected[0]['x']['unit'][3]==2.5


def test_pending_not_scored_and_same_rows_baseline_is_used():
    result=research.score([item(),item(game='pending',y=None)],lambda x:.8)
    assert result['observations']==1
    assert result['brier']==pytest.approx(.04)
    assert result['same_rows_market_brier']==.25
    assert result['game_cluster_95'] is None
    assert research.score([item()],lambda x:None)['observations']==0


def test_cluster_interval_resamples_whole_games(monkeypatch):
    monkeypatch.setitem(research.PROTOCOL,'bootstrap_samples',1000)
    assert research.cluster_interval({'a':[1]*10,'b':[-1]})==[-1,1]
    assert research.cluster_interval({'a':[1],'b':[-1]})==[-1,1]


def test_offline_ledger_cannot_create_or_write_and_closes(tmp_path):
    missing=tmp_path/'missing.db'
    with pytest.raises(ValueError):research.OfflineLedger(missing)
    assert not missing.exists()
    path=tmp_path/'existing.db'
    db=sqlite3.connect(path);db.execute('CREATE TABLE example (value INTEGER)');db.close()
    ledger=research.OfflineLedger(path)
    with ledger.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM example').fetchone()==(0,)
        with pytest.raises(sqlite3.OperationalError):connection.execute('INSERT INTO example VALUES (1)')
    with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')


def test_same_name_with_different_player_id_cannot_supply_opposite():
    over=without_retained_baseline(payload(prediction_id='over'))
    under=without_retained_baseline(payload('under','under',player_id='00-2'))
    assert research.observations([over,under],'nfl','empirical-jeffreys-v4')[0]==[]
