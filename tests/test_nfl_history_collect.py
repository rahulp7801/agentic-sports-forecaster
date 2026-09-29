import copy,json
from datetime import timedelta

import httpx
import pytest

from sportsbet.quant import nfl_history_collect as collector
from sportsbet.ingestion.nfl_final_evidence import digest,inspect_bundle
from tests.test_nfl_final_evidence import bundle,NOW,PLAYER,EVENT,source,CORE


def fixture():
    b=bundle();s=b['participation'][0]
    data=dict(identity=b['identity'],observed_at=NOW.isoformat(),cutoff='2026-09-23',season_floor=2024,
        players=[dict(player_id=PLAYER,pfr_player_id='TrauAd00',player='Adam Trautman',current_quoted=True)],stats=[],
        snaps=[dict(game_id=s['row']['game_id'],game_date=s['game_date'],home_team=s['home_team'],away_team=s['away_team'],
            snap=s['row']|{k:s[k] for k in ('source_provider','source_sha256','source_record_sha256','source_observed_at')})])
    comp=json.loads(b['sources'][0]['response_text'])['header']['competitions'][0]
    board=source(collector.SITE+'scoreboard?dates=20260920&limit=100',dict(events=[dict(id=EVENT,competitions=[comp])]))
    return b,data,board


def cache(tmp_path):
    b,data,board=fixture();c=collector.ReceiptCache(tmp_path,now=lambda:NOW)
    for s in [board,*b['sources']]:c.retain(s)
    return c,data


def test_offline_explicit_zero_bundle_passes_unchanged_import_contract(tmp_path):
    c,data=cache(tmp_path);before=copy.deepcopy(data)
    result=collector.collect(data,c)
    assert result['requests']==0 and result['unresolved']==[] and result['requested_games']==1
    evidence,=inspect_bundle(result['bundles'][PLAYER],now=NOW)
    assert evidence['stat_row']['receptions']==0 and evidence['stat_row']['receiving_yards']==0
    assert data==before


def test_missing_stats_are_unknown_and_partial_receipts_retained(tmp_path):
    c,data=cache(tmp_path);b,_,_=fixture();url=b['sources'][-1]['url']
    (tmp_path/(digest(url)+'.json')).unlink()
    result=collector.collect(data,c)
    assert result['bundles']=={} and len(result['unresolved'])==1 and result['requests']==0
    assert (tmp_path/(digest(b['sources'][0]['url'])+'.json')).exists()


@pytest.mark.parametrize('url',[
    'https://evil.example/steal','http://site.api.espn.com/anything',
    collector.SITE+'summary?event=1&apiKey=secret',
    'https://site.api.espn.com@evil.example/nfl',
    collector.SITE+'summary?event=1#fragment',
])
def test_out_of_scope_url_never_fetches(tmp_path,url):
    def fail(request):raise AssertionError('Unexpected network request')
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        c=collector.ReceiptCache(tmp_path,client=client,now=lambda:NOW)
        with pytest.raises(ValueError):c.read(url)
        assert c.requests==0


def test_receipt_cache_reuses_exact_bytes_and_observation(tmp_path):
    calls=[];url=collector.SITE+'summary?event=1'
    def handler(request):calls.append(str(request.url));return httpx.Response(200,content=b'{"ok": true}')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        c=collector.ReceiptCache(tmp_path,client=client,now=lambda:NOW)
        first=c.read(url);second=c.read(url)
        assert first==second and len(calls)==1 and first['response_text']=='{"ok": true}'
        assert first['sha256']==digest(first['response_text'])


def test_stale_dependent_receipt_is_refreshed_after_observed_final(tmp_path):
    url=collector.SITE+'summary?event=1';s=source(url,{})
    s['observed_at']=(NOW-timedelta(minutes=1)).isoformat()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'new':True}))) as client:
        c=collector.ReceiptCache(tmp_path,client=client,now=lambda:NOW);c.retain(s)
        assert c.read(url,not_before=NOW)['observed_at']==NOW.isoformat() and c.requests==1


@pytest.mark.parametrize('mode',['redirect','oversized','invalid_json','future','tampered','budget'])
def test_cache_network_and_commitment_bounds(tmp_path,monkeypatch,mode):
    url=collector.SITE+'summary?event=1'
    if mode=='oversized':monkeypatch.setattr(collector,'MAX_RESPONSE_BYTES',8)
    def handler(request):
        if mode=='redirect':return httpx.Response(302,headers={'location':'https://evil.example'})
        return httpx.Response(200,content=b'not json' if mode=='invalid_json' else b'{"too_large":true}')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        c=collector.ReceiptCache(tmp_path,client=client,now=lambda:NOW)
        if mode in ('future','tampered'):
            s=source(url,{})
            if mode=='future':s['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
            else:s['sha256']='a'*64
            (tmp_path/(digest(url)+'.json')).write_text(json.dumps(s),encoding='utf-8')
        if mode=='budget':c.requests=collector.MAX_REQUESTS
        with pytest.raises((ValueError,httpx.HTTPError)):c.read(url)
        assert c.requests<=collector.MAX_REQUESTS


def test_corrupt_participation_rejected_before_fetch(tmp_path):
    c,data=cache(tmp_path);data['snaps'][0]['snap']['offense_snaps']=0
    with pytest.raises(ValueError):collector.collect(data,c)
    assert c.requests==0


def test_ambiguous_scoreboard_and_wrong_stat_reference_stay_unresolved(tmp_path):
    c,data=cache(tmp_path);b,_,board=fixture()
    raw=json.loads(board['response_text']);raw['events']*=2
    changed=source(board['url'],raw)
    (tmp_path/(digest(board['url'])+'.json')).write_text(json.dumps(changed),encoding='utf-8')
    assert collector.collect(data,c)['bundles']=={}
    (tmp_path/(digest(board['url'])+'.json')).write_text(json.dumps(board),encoding='utf-8')
    receipt=b['sources'][1];roster=json.loads(receipt['response_text']);roster['entries'][0]['statistics']['$ref']='https://evil.example/stats'
    changed=source(receipt['url'],roster)
    (tmp_path/(digest(receipt['url'])+'.json')).write_text(json.dumps(changed),encoding='utf-8')
    assert collector.collect(data,c)['bundles']=={} and c.requests==0


def test_explicit_nonzero_values_are_preserved(tmp_path):
    c,data=cache(tmp_path);b,_,_=fixture();receipt=b['sources'][-1]
    stats=json.loads(receipt['response_text']);stats['splits']['categories'][1]['stats'][0]['value']=2
    stats['splits']['categories'][1]['stats'][1]['value']=17
    changed=source(receipt['url'],stats)
    (tmp_path/(digest(receipt['url'])+'.json')).write_text(json.dumps(changed),encoding='utf-8')
    result=collector.collect(data,c);e,=inspect_bundle(result['bundles'][PLAYER],now=NOW)
    assert e['stat_row']['receptions']==2 and e['stat_row']['receiving_yards']==17


def test_scope_bound_checked_before_collection(tmp_path,monkeypatch):
    c,data=cache(tmp_path);monkeypatch.setattr(collector,'MAX_GAPS',0)
    with pytest.raises(ValueError,match='scope'):collector.collect(data,c)
    assert c.requests==0
