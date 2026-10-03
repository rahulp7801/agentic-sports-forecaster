from datetime import datetime, timedelta, timezone
import hashlib
import json
from copy import deepcopy

import httpx
import pytest

from sportsbet.quant import kalshi_stat_only_context_refresh as refresh
from sportsbet.quant import kalshi_stat_only_teammate_context as context
from sportsbet.quant.kalshi_market_cohort import digest

NOW = datetime(2026, 10, 4, 10, 45, tzinfo=timezone.utc)


def valid_proof():
    before=NOW-timedelta(seconds=1)
    return dict(protocol=refresh.CLOCK_VERSION, checked_at=NOW.isoformat(),
        local_clock_acceptable=True, observations=[dict(host=host,
            request_started_at=before.isoformat(), response_received_at=NOW.isoformat(),
            server_date=NOW.isoformat(), rtt_seconds=1.0,
            server_minus_local_seconds=.5, age=None, http_status=200)
            for host in refresh.HOSTS])

class RecordedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return (NOW+timedelta(seconds=1)).astimezone(tz)



def item(name, url, raw, updated='2026-10-03T12:30:28+00:00'):
    return dict(name=name, browser_download_url=url, digest='sha256:'+hashlib.sha256(raw).hexdigest(),
                size=len(raw), state='uploaded', id=10, updated_at=updated)


def test_release_asset_requires_exact_identity_digest_and_pregame_time():
    url='https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/sample.parquet'
    raw=b'original'
    asset=item('sample.parquet', url, raw)
    baseline=hashlib.sha256(raw).hexdigest()
    got=refresh.validate_asset({'assets':[asset]},'weekly_rosters','sample.parquet',url,
                               baseline,asset['updated_at'],NOW)
    assert got['changed_from_baseline'] is False
    with pytest.raises(ValueError,match='ambiguous'):
        refresh.validate_asset({'assets':[asset,asset]},'weekly_rosters','sample.parquet',url,
                               baseline,asset['updated_at'],NOW)
    with pytest.raises(ValueError,match='chronology'):
        refresh.validate_asset({'assets':[dict(asset,updated_at='2026-10-04T13:30:00+00:00')]},
                               'weekly_rosters','sample.parquet',url,baseline,asset['updated_at'],NOW)
    with pytest.raises(ValueError,match='changed bytes'):
        refresh.validate_asset({'assets':[dict(asset,digest='sha256:'+'1'*64)]},
                               'weekly_rosters','sample.parquet',url,baseline,asset['updated_at'],NOW)


def test_unchanged_public_assets_reuse_pinned_baseline_without_download(tmp_path,monkeypatch):
    source=[]
    for tag in ('injuries','weekly_rosters'):
        filename=tag+'.parquet'; raw=tag.encode(); url='https://github.com/nflverse/nflverse-data/releases/download/'+tag+'/'+filename
        source.append((tag,filename,url,hashlib.sha256(raw).hexdigest(),'2026-10-03T12:30:28+00:00'))
    monkeypatch.setattr(refresh,'SOURCES',tuple(source))
    monkeypatch.setattr(refresh,'datetime',RecordedDatetime)
    base=tmp_path/'baseline';base.mkdir()
    for tag,filename,*_ in source:(base/filename).write_bytes(tag.encode())
    receipt={'first_kickoff_at':'2026-10-04T13:30:00+00:00'}
    expected=digest(receipt);receipt['record_sha256']=expected
    monkeypatch.setattr(context,'EXPECTED_RECORD_SHA256',expected)
    monkeypatch.setattr(refresh,'download_asset',lambda *args:pytest.fail('Unchanged asset downloaded'))
    def handler(request):
        tag=request.url.path.rsplit('/',1)[-1]
        row=next(s for s in source if s[0]==tag)
        data={'assets':[item(row[1],row[2],tag.encode())]}
        return httpx.Response(200,json=data)
    proof=valid_proof()
    for field,value in [('rtt_seconds',True),('age',False)]:
        invalid=valid_proof()
        invalid['observations'][0][field]=value
        with httpx.Client(transport=httpx.MockTransport(
                lambda request:pytest.fail('Invalid clock triggered a release read')),
                follow_redirects=False) as client:
            with pytest.raises(ValueError,match='clock observation'):
                refresh.stage(tmp_path/'invalid',base,receipt,now=NOW,client=client,
                              clock_proof=invalid)
    assert not (tmp_path/'invalid').exists()
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        result=refresh.stage(tmp_path/'output',base,receipt,now=NOW,client=client,
                             clock_proof=proof)
    assert {x['retrieval'] for x in result['assets'].values()}=={'copied_pinned_baseline'}
    assert result['record_sha256']==digest({k:v for k,v in result.items() if k!='record_sha256'})
    assert (tmp_path/'output'/'receipt.json').is_file()
    result['recorded_at']=(NOW+timedelta(seconds=1)).isoformat()
    result['record_sha256']=digest({k:v for k,v in result.items() if k!='record_sha256'})
    (tmp_path/'output'/'receipt.json').write_text(json.dumps(result))
    assert refresh.verify(tmp_path/'output',receipt)==result
    changed=deepcopy(result)
    changed['clock_proof']['observations'][0]['rtt_seconds']=True
    changed['record_sha256']=digest({k:v for k,v in changed.items() if k!='record_sha256'})
    (tmp_path/'output'/'receipt.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='clock observation'):
        refresh.verify(tmp_path/'output',receipt)
    (tmp_path/'output'/'receipt.json').write_text(json.dumps(result))
    for tag in ('injuries','weekly_rosters'):
        raw=(tmp_path/'output'/f'{tag}-release.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==result['release_metadata_sha256'][tag]
    (tmp_path/'output'/'injuries-release.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Raw release metadata changed'):
        refresh.verify(tmp_path/'output',receipt)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError,match='not authorized'):
            refresh.stage(tmp_path/'other',base,receipt,
                          now=datetime(2026,10,4,13,35,tzinfo=timezone.utc),
                          client=client,clock_proof={'local_clock_acceptable':True,'checked_at':NOW.isoformat()})

def test_changed_asset_downloads_once_at_pinned_digest(tmp_path,monkeypatch):
    tag='injuries'; filename='injuries.parquet'
    url='https://github.com/nflverse/nflverse-data/releases/download/injuries/'+filename
    old=b'old'; new=b'new source bytes'
    source=(tag,filename,url,hashlib.sha256(old).hexdigest(),'2026-10-03T12:30:28+00:00')
    monkeypatch.setattr(refresh,'SOURCES',(source,))
    monkeypatch.setattr(refresh,'datetime',RecordedDatetime)
    base=tmp_path/'baseline';base.mkdir();(base/filename).write_bytes(old)
    receipt={'first_kickoff_at':'2026-10-04T13:30:00+00:00'}
    receipt['record_sha256']=digest(receipt)
    monkeypatch.setattr(context,'EXPECTED_RECORD_SHA256',receipt['record_sha256'])
    calls=[]
    def download(client,target,expected):
        calls.append((target,expected))
        return new
    monkeypatch.setattr(refresh,'download_asset',download)
    def handler(request):
        assert 'authorization' not in request.headers
        return httpx.Response(200,json={'assets':[item(filename,url,new,
            updated='2026-10-04T07:00:00+00:00')]})
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        report=refresh.stage(tmp_path/'output',base,receipt,now=NOW,client=client,
                             clock_proof=valid_proof())
    assert calls==[(url,hashlib.sha256(new).hexdigest())]
    assert (tmp_path/'output'/filename).read_bytes()==new
    assert report['assets'][tag]['retrieval']=='downloaded_changed_public_asset'
    raw=(tmp_path/'output'/f'{tag}-release.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==report['release_metadata_sha256'][tag]
