from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from sportsbet import market_watch


NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


def game(number: int, *events: str) -> dict:
    return {
        'id': f'00000000-0000-0000-0000-00000000000{number}',
        'start_date': (NOW + timedelta(days=1)).isoformat(),
        'related_event_tickers': list(events),
        'details': {'league': 'NFL','home_team_id':'10000000-0000-0000-0000-000000000001',
            'away_team_id':'20000000-0000-0000-0000-000000000002'},
    }


def market(series: str, event: str, suffix: str) -> dict:
    return {
        'ticker': f'{event}-{suffix}',
        'event_ticker': event,
        'status': 'active',
        'market_type': 'binary',
        'notional_value_dollars': '1.0000',
        'primary_participant_key':'football_player',
        'custom_strike':{'football_player':'30000000-0000-0000-0000-000000000003',
            'football_team':'10000000-0000-0000-0000-000000000001'},
        'strike_type':'greater','floor_strike':249.5,
        'occurrence_datetime':(NOW+timedelta(days=1)).isoformat(),
        'yes_bid_dollars':'0.4000','yes_bid_size_fp':'12.00',
        'yes_ask_dollars':'0.4500','yes_ask_size_fp':'10.00',
        'no_bid_dollars':'0.5500','no_ask_dollars':'0.6000',
        'rules_primary':'Primary settlement rule.','rules_secondary':'Secondary settlement rule.',
    }


def configure_targets(reader: AsyncMock) -> None:
    reader.targets.return_value={'structured_targets':[{
        'id':'30000000-0000-0000-0000-000000000003','name':'Player Name','type':'football_player',
        'details':{'league':'NFL','team_id':'10000000-0000-0000-0000-000000000001'}}],'cursor':''}
    async def series(name):
        return {'ticker':name,'fee_type':'quadratic','fee_multiplier':1,
            'last_updated_ts':(NOW-timedelta(days=1)).isoformat()}
    reader.series.side_effect=series
    reader.series_fee_changes.return_value={'series_fee_change_arr':[]}
    reader.event_fee_changes.return_value={'event_fee_changes':[],'cursor':''}


@pytest.mark.asyncio
async def test_prop_inventory_links_structured_events_and_reports_complete_pages():
    passing = 'KXNFLPASSYDS-26SEP13ATLPIT'
    rushing = 'KXNFLRSHYDS-26SEP13ATLPIT'
    reader = AsyncMock()
    configure_targets(reader)

    async def pages(series, *, limit, cursor=None):
        assert limit == market_watch.PROP_PAGE_LIMIT
        if series == 'KXNFLPASSYDS':
            if cursor is None:
                return {'markets': [market(series, passing, 'PLAYER-250')], 'cursor': 'next'}
            assert cursor == 'next'
            return {'markets': [market(series, passing, 'PLAYER-275')], 'cursor': ''}
        if series == 'KXNFLRSHYDS':
            return {'markets': [market(series, rushing, 'PLAYER-50')], 'cursor': ''}
        return {'markets': [], 'cursor': ''}

    reader.markets.side_effect = pages
    result = await market_watch.kalshi_prop_inventory(
        reader,
        'nfl',
        [game(1, passing, rushing, 'KXNFLTOTAL-26SEP13ATLPIT')],
    )

    assert result['status'] == 'observed'
    assert result['partial_coverage'] is False
    assert result['coverage'] == {
        'series_expected': 4,
        'series_observed': 4,
        'open_markets': 3,
        'open_events': 2,
        'linked_markets': 3,
        'linked_events': 2,
        'structured_quote_markets': 3,
        'yes_ask_quote_markets': 3,
        'no_ask_quote_markets': 3,
        'two_sided_quote_markets': 3,
        'one_sided_quote_markets': 0,
        'unquoted_markets': 0,
        'player_resolved_quote_markets': 3,
        'fee_contexts_expected': 2,
        'fee_contexts_observed': 2,
        'discovery_complete': True,
    }
    assert result['series']['KXNFLPASSYDS']['pages'] == 2
    assert result['series']['KXNFLPASSYDS']['linked_markets'] == 2
    assert result['series']['KXNFLPASSYDS']['response_sha256']
    assert 'markets' not in result['series']['KXNFLPASSYDS']
    assert len(result['quotes'])==3
    quote=result['quotes'][0]
    assert {k:v for k,v in quote.items() if k not in ('request_started_at','received_at')} == {
        'ticker':f'{passing}-PLAYER-250','event_ticker':passing,'series_ticker':'KXNFLPASSYDS',
        'milestone_id':game(1)['id'],'scheduled_game_start_time':(NOW+timedelta(days=1)).isoformat(),
        'market_occurrence_time':(NOW+timedelta(days=1)).isoformat(),
        'prop_type':'pass_yds','player_target_id':'30000000-0000-0000-0000-000000000003',
        'team_target_id':'10000000-0000-0000-0000-000000000001','strike_type':'greater','line':'249.5',
        'yes_ask':{'cost':'0.4500','displayed_size':'10.00'},
        'no_ask':{'cost':'0.6000','displayed_size':'12.00'},
        'market_sha256':market_watch.digest(market('KXNFLPASSYDS',passing,'PLAYER-250')),
        'source_page_sha256':quote['source_page_sha256'],
        'settlement_rules':{'primary':'Primary settlement rule.','secondary':'Secondary settlement rule.'},
        'rules_sha256':market_watch.digest({'primary':'Primary settlement rule.','secondary':'Secondary settlement rule.'}),
        'settlement_terms':{'schema_version':1,
            'rules_sha256':market_watch.digest({'primary':'Primary settlement rule.','secondary':'Secondary settlement rule.'}),
            'participation':'unclassified','statistic':'unclassified','overtime':'unspecified',
            'stat_corrections':'unspecified','stat_source':'unspecified','classified':False},
        'settlement_equivalent':False,'execution_ready':False}
    assert datetime.fromisoformat(quote['request_started_at']) <= datetime.fromisoformat(quote['received_at'])
    target=result['targets']['30000000-0000-0000-0000-000000000003']
    assert target['player_name']=='Player Name'
    assert target['team_target_id']=='10000000-0000-0000-0000-000000000001'
    assert target['target_sha256']==market_watch.digest(reader.targets.return_value['structured_targets'][0])
    assert datetime.fromisoformat(target['target_request_started_at']) <= datetime.fromisoformat(target['target_received_at'])
    assert reader.markets.await_count == 5
    assert set(result['fee_contexts'])=={passing,rushing}
    assert result['fee_failures']==[]
    assert all(context['event_ticker'] in (passing,rushing) for context in result['fee_contexts'].values())


def test_prop_quote_coverage_partitions_market_and_side_availability():
    quotes=[{'yes_ask':{},'no_ask':{}},{'yes_ask':{},'no_ask':None},
        {'yes_ask':None,'no_ask':{}},{'yes_ask':None,'no_ask':None}]
    coverage=market_watch.kalshi_prop_quote_coverage(quotes)
    assert coverage==dict(structured_quote_markets=4,yes_ask_quote_markets=2,
        no_ask_quote_markets=2,two_sided_quote_markets=1,one_sided_quote_markets=2,
        unquoted_markets=1)
    assert coverage['structured_quote_markets']==sum(coverage[key] for key in (
        'two_sided_quote_markets','one_sided_quote_markets','unquoted_markets'))
    assert coverage['yes_ask_quote_markets']+coverage['no_ask_quote_markets']==(
        2*coverage['two_sided_quote_markets']+coverage['one_sided_quote_markets'])


def test_nfl_prop_rule_classifier_preserves_explicit_no_snap_risk():
    rules={'primary':'Exact primary condition.','secondary':(
        'If Player is active but never takes a snap, the market settles to the fair market price before game start. '
        'Once Player takes at least one snap, even if nullified by penalty, the market settles based on passing yards recorded.')}
    terms=market_watch.classify_prop_settlement_rules(rules,'pass_yds')
    assert terms['participation']=='active_no_snap_fair_market_price'
    assert terms['statistic']=='after_one_snap_recorded_stat'
    assert terms['classified'] is True and terms['overtime']=='unspecified'
    assert terms['stat_corrections']=='unspecified' and terms['stat_source']=='unspecified'
    assert terms['rules_sha256']==market_watch.digest(rules)


@pytest.mark.asyncio
async def test_prop_inventory_preserves_counts_but_fails_closed_on_incomplete_or_bad_pages():
    event = 'KXNFLPASSYDS-26SEP13ATLPIT'
    reader = AsyncMock()
    configure_targets(reader)

    async def pages(series, *, limit, cursor=None):
        if series == 'KXNFLPASSYDS':
            if cursor is None:
                return {'markets': [market(series, event, 'PLAYER-250')], 'cursor': 'repeat'}
            return {'markets': [], 'cursor': 'repeat'}
        if series == 'KXNFLRSHYDS':
            return {'markets': 'not-a-list', 'cursor': ''}
        if series == 'KXNFLRECYDS':
            raise RuntimeError('provider URL with private material')
        return {'markets': [], 'cursor': ''}

    reader.markets.side_effect = pages
    result = await market_watch.kalshi_prop_inventory(reader, 'nfl', [game(1, event)])

    assert result['status'] == 'degraded'
    assert result['partial_coverage'] is True
    assert result['coverage']['linked_markets'] == 1
    assert result['coverage']['structured_quote_markets'] == 1
    assert result['coverage']['player_resolved_quote_markets'] == 1
    assert result['coverage']['discovery_complete'] is False
    assert result['series']['KXNFLPASSYDS']['complete'] is False
    assert result['series']['KXNFLRSHYDS']['status'] == 'invalid'
    assert result['series']['KXNFLRECYDS']['status'] == 'unavailable'
    assert 'private material' not in str(result)
    assert reader.markets.await_count <= 6


@pytest.mark.asyncio
async def test_prop_inventory_rejects_cross_game_event_conflicts():
    event = 'KXNFLPASSYDS-26SEP13ATLPIT'
    reader = AsyncMock()
    async def pages(series, **kwargs):
        return {'markets': [market(series, event, 'PLAYER-250')] if series == 'KXNFLPASSYDS' else [], 'cursor': ''}
    reader.markets.side_effect = pages
    result = await market_watch.kalshi_prop_inventory(
        reader,
        'nfl',
        [game(1, event), game(2, event)],
    )
    assert result['status'] == 'degraded'
    assert result['coverage']['open_markets'] == 1
    assert result['coverage']['linked_markets'] == 0
    assert result['coverage']['discovery_complete'] is False
    assert result['failures'] == [{'stage': 'prop_link', 'error_type': 'ConflictingEvent'}]


@pytest.mark.asyncio
async def test_prop_inventory_validates_sport_and_milestone_shape():
    reader = AsyncMock()
    with pytest.raises(ValueError):
        await market_watch.kalshi_prop_inventory(reader, 'mlb', [])
    reader.markets.return_value = {'markets': [], 'cursor': ''}
    result = await market_watch.kalshi_prop_inventory(reader, 'nfl', [{'id': 'game'}])
    assert result['status'] == 'degraded'
    assert result['coverage']['discovery_complete'] is False
    assert result['failures'] == [{'stage': 'prop_link', 'error_type': 'InvalidMilestone'}]
    assert reader.markets.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('change,reason',[({'yes_ask_dollars':'0.4600'},'inconsistent_prop_top_of_book'),
    ({'custom_strike':{'football_player':'30000000-0000-0000-0000-000000000003',
        'football_team':'90000000-0000-0000-0000-000000000009'}},'prop_team_mismatch'),
    ({'primary_participant_key':'football_team'},'prop_participant_mismatch')])
async def test_prop_inventory_rejects_inconsistent_quote_or_structured_identity(change,reason):
    event='KXNFLPASSYDS-26SEP13ATLPIT';reader=AsyncMock()
    item=market('KXNFLPASSYDS',event,'PLAYER-250')|change
    async def pages(series,**kwargs):
        return {'markets':[item] if series=='KXNFLPASSYDS' else [],'cursor':''}
    reader.markets.side_effect=pages
    result=await market_watch.kalshi_prop_inventory(reader,'nfl',[game(1,event)])
    assert result['status']=='degraded' and result['partial_coverage'] is True
    assert result['coverage']['structured_quote_markets']==0
    assert result['series']['KXNFLPASSYDS']['status']=='invalid'
    assert result['failures']==[{'stage':'prop_discovery','series':'KXNFLPASSYDS',
        'error_type':'ValueError','reason':reason}]


@pytest.mark.asyncio
async def test_prop_target_failure_retains_quotes_but_blocks_cross_provider_identity():
    event='KXNFLPASSYDS-26SEP13ATLPIT';reader=AsyncMock()
    async def pages(series,**kwargs):
        return {'markets':[market(series,event,'PLAYER-250')] if series=='KXNFLPASSYDS' else [],'cursor':''}
    reader.markets.side_effect=pages
    reader.targets.return_value={'structured_targets':[],'cursor':''}
    result=await market_watch.kalshi_prop_inventory(reader,'nfl',[game(1,event)])
    assert result['status']=='degraded' and result['coverage']['structured_quote_markets']==1
    assert result['coverage']['player_resolved_quote_markets']==0
    assert 'player_name' not in result['quotes'][0]
    assert result['targets']=={}
    assert result['failures']==[{'stage':'prop_targets','error_type':'ValueError',
        'reason':'incomplete_structured_target_page'}]


@pytest.mark.asyncio
async def test_fee_failure_preserves_quote_inventory_and_is_reported_separately():
    event='KXNFLPASSYDS-26SEP13ATLPIT';reader=AsyncMock()
    configure_targets(reader)
    async def pages(series,**kwargs):
        return {'markets':[market(series,event,'PLAYER-250')] if series=='KXNFLPASSYDS' else [],'cursor':''}
    reader.markets.side_effect=pages
    reader.event_fee_changes.side_effect=RuntimeError('private provider detail')
    result=await market_watch.kalshi_prop_inventory(reader,'nfl',[game(1,event)])
    assert result['status']=='observed' and result['partial_coverage'] is False
    assert result['coverage']['structured_quote_markets']==1
    assert result['coverage']['fee_contexts_expected']==1
    assert result['coverage']['fee_contexts_observed']==0
    assert result['fee_contexts']=={}
    assert result['fee_failures']==[{'stage':'prop_fees','series':'KXNFLPASSYDS',
        'event_ticker':event,'error_type':'RuntimeError'}]
    assert 'private provider detail' not in str(result)


def sport_prop(sport, suffix):
    series=next(iter(market_watch.KALSHI_PROP_SERIES[sport]))
    event=series+'-MOCK'
    milestone=game(1,event)
    milestone['details']['league']=sport.upper()
    value=market(series,event,suffix)
    if sport=='nba':
        value['primary_participant_key']='basketball_player'
        value['custom_strike']={key.replace('football','basketball'):item
            for key,item in value['custom_strike'].items()}
    return series,milestone,value


def sport_reader(sport, selected_series, page):
    reader=AsyncMock()
    configure_targets(reader)
    if sport=='nba':
        target=reader.targets.return_value['structured_targets'][0]
        target['type']='basketball_player';target['details']['league']='NBA'
    async def pages(series, *, limit, cursor=None):
        assert limit==market_watch.PROP_PAGE_LIMIT
        assert cursor is None  # An invalid page must never advance pagination.
        return page if series==selected_series else {'markets':[],'cursor':''}
    reader.markets.side_effect=pages
    return reader


@pytest.mark.asyncio
@pytest.mark.parametrize('sport',['nfl','nba'])
@pytest.mark.parametrize('cursor',['','next-page-must-not-be-read'])
@pytest.mark.parametrize('bad_count',[1,2])
async def test_invalid_quotes_preserve_valid_siblings_only_on_the_received_page(sport,cursor,bad_count):
    series,milestone,good=sport_prop(sport,'GOOD')
    rejected=[]
    for number in range(bad_count):
        value=deepcopy(good)
        value['ticker']=value['event_ticker']+f'-BAD{number}'
        value['strike_type']='structured'  # Still rejected, never reinterpreted.
        rejected.append(value)
    last=deepcopy(good);last['ticker']=last['event_ticker']+'-LAST'
    page={'markets':rejected[:1]+[good]+rejected[1:]+[last],'cursor':cursor}
    reader=sport_reader(sport,series,page)
    result=await market_watch.kalshi_prop_inventory(reader,sport,[milestone])
    assert result['status']=='degraded' and result['partial_coverage'] is True
    assert result['coverage']['discovery_complete'] is False
    assert result['coverage']['series_observed']==len(market_watch.KALSHI_PROP_SERIES[sport])-1
    assert result['coverage']['open_markets']==result['coverage']['linked_markets']==bad_count+2
    assert result['coverage']['structured_quote_markets']==result['coverage']['player_resolved_quote_markets']==2
    assert result['series'][series]==dict(status='invalid',complete=False,pages=1,
        open_markets=bad_count+2,open_events=1,linked_markets=bad_count+2,linked_events=1,
        response_sha256=market_watch.digest([page]))
    assert [quote['ticker'] for quote in result['quotes']]==[good['ticker'],last['ticker']]
    assert all(quote['execution_ready'] is False and quote['settlement_equivalent'] is False
        for quote in result['quotes'])
    assert result['failures']==[dict(stage='prop_discovery',series=series,error_type='ValueError',
        reason='prop_strike_type_mismatch')]*bad_count
    assert reader.markets.await_count==len(market_watch.KALSHI_PROP_SERIES[sport])
    reader.targets.assert_awaited_once_with(['30000000-0000-0000-0000-000000000003'])


@pytest.mark.asyncio
@pytest.mark.parametrize('sport',['nfl','nba'])
@pytest.mark.parametrize('corruption',['duplicate','rejected_duplicate','identity','page','cursor'])
async def test_page_identity_and_duplicate_corruption_still_abort_immediately(sport,corruption):
    series,milestone,good=sport_prop(sport,'GOOD')
    last=deepcopy(good);last['ticker']=last['event_ticker']+'-MUST-NOT-BE-PARSED'
    if corruption=='duplicate':
        page={'markets':[good,deepcopy(good),last],'cursor':'must-not-follow'}
    elif corruption=='rejected_duplicate':
        rejected=deepcopy(good);rejected['strike_type']='structured'
        page={'markets':[rejected,good,last],'cursor':'must-not-follow'}
    elif corruption=='identity':
        invalid=deepcopy(good);invalid['market_type']='scalar'
        page={'markets':[invalid,last],'cursor':'must-not-follow'}
    elif corruption=='page':
        page={'markets':'invalid-page','cursor':'must-not-follow'}
    else:
        page={'markets':[good,last],'cursor':[]}
    reader=sport_reader(sport,series,page)
    result=await market_watch.kalshi_prop_inventory(reader,sport,[milestone])
    assert result['status']=='degraded' and result['partial_coverage'] is True
    assert result['coverage']['discovery_complete'] is False
    assert result['series'][series]['status']=='invalid' and result['series'][series]['complete'] is False
    expected=[good['ticker']] if corruption=='duplicate' else []
    assert [quote['ticker'] for quote in result['quotes']]==expected
    reason={'duplicate':'invalid_prop_market_identity','rejected_duplicate':'invalid_prop_market_identity',
        'identity':'invalid_prop_market_identity',
        'page':'invalid_market_page','cursor':'invalid_market_cursor'}[corruption]
    expected_failures=[dict(stage='prop_discovery',series=series,error_type='ValueError',reason=reason)]
    if corruption=='rejected_duplicate':
        expected_failures.insert(0,dict(stage='prop_discovery',series=series,error_type='ValueError',
            reason='prop_strike_type_mismatch'))
    assert result['failures']==expected_failures
    assert reader.markets.await_count==len(market_watch.KALSHI_PROP_SERIES[sport])
    if expected:
        reader.targets.assert_awaited_once()
    else:
        reader.targets.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('sport',['nfl','nba'])
async def test_target_failure_after_quote_isolation_keeps_valid_quote_partial_and_unresolved(sport):
    series,milestone,good=sport_prop(sport,'GOOD')
    bad=deepcopy(good);bad['ticker']=bad['event_ticker']+'-BAD';bad['strike_type']='structured'
    reader=sport_reader(sport,series,{'markets':[bad,good],'cursor':'must-not-follow'})
    reader.targets.return_value={'structured_targets':[],'cursor':''}
    result=await market_watch.kalshi_prop_inventory(reader,sport,[milestone])
    assert result['status']=='degraded' and result['partial_coverage'] is True
    assert result['series'][series]['status']=='invalid' and result['series'][series]['complete'] is False
    assert result['coverage']['discovery_complete'] is False
    assert result['coverage']['structured_quote_markets']==1
    assert result['coverage']['player_resolved_quote_markets']==0 and result['targets']=={}
    assert [quote['ticker'] for quote in result['quotes']]==[good['ticker']]
    assert result['failures']==[
        dict(stage='prop_discovery',series=series,error_type='ValueError',reason='prop_strike_type_mismatch'),
        dict(stage='prop_targets',error_type='ValueError',reason='incomplete_structured_target_page')]
    assert reader.markets.await_count==len(market_watch.KALSHI_PROP_SERIES[sport])
    reader.targets.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('sport',['nfl','nba'])
async def test_unexpected_quote_error_keeps_original_unavailable_abort(monkeypatch,sport):
    series,milestone,good=sport_prop(sport,'GOOD')
    later=deepcopy(good);later['ticker']=later['event_ticker']+'-MUST-NOT-BE-PARSED'
    reader=sport_reader(sport,series,{'markets':[good,later],'cursor':'must-not-follow'})
    parsed=[]
    def unexpected(value,*args):
        parsed.append(value['ticker'])
        raise RuntimeError('private provider material must not appear')
    monkeypatch.setattr(market_watch,'kalshi_prop_quote',unexpected)
    result=await market_watch.kalshi_prop_inventory(reader,sport,[milestone])
    assert parsed==[good['ticker']]
    assert result['series'][series]['status']=='unavailable' and result['series'][series]['complete'] is False
    assert result['status']=='degraded' and result['partial_coverage'] is True
    assert result['coverage']['discovery_complete'] is False and result['quotes']==[]
    assert result['failures']==[dict(stage='prop_discovery',series=series,error_type='RuntimeError')]
    assert 'private provider material' not in str(result)
    assert reader.markets.await_count==len(market_watch.KALSHI_PROP_SERIES[sport])
    reader.targets.assert_not_awaited()
