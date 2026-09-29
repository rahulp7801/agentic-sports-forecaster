import json
from copy import deepcopy
import pytest
from sportsbet.ingestion.cfb_supplement_proof import valid_supplement, _sha
from sportsbet.quant.cfb_history_supplements import plan_supplements
from tests.test_cfb_final_evidence import bundle, NOW
from tests.test_cfb_history_completeness import primary


def fixture():
    row=primary()
    item,=plan_supplements(json.dumps(bundle()),[row],now=NOW)['updates']
    return row | dict(receiving_yards=0,receptions=0),item


def valid(row,item):
    return valid_supplement(row,item['manifest'],item['source_sha256'],
        item['observed_at'],'2026-09-26T16:00:00Z')


def test_composite_reproduces_both_stat_records_and_source_receipts():
    row,item=fixture()
    assert valid(row,item)
    for key,value in [('rushing_yards',69),('receiving_yards',1),('athlete_id',202)]:
        assert not valid(row | {key:value},item)
    assert not valid(row,item | {'observed_at':'2026-09-27T00:00:00Z'})
    assert not valid(row,item | {'manifest':None})


@pytest.mark.parametrize('case', ['primary_hash','asset_hash','policy','wrong_event',
    'wrong_url','future_receipt','activity','boolean_stat','missing_source','malformed_sources'])
def test_rehashed_manifest_still_requires_valid_internal_commitments(case):
    row,item=fixture();m=item['manifest'];e=m['explicit_source']
    if case=='primary_hash': m['primary_record_sha256']='f'*64
    if case=='asset_hash': m['primary_player_sha256']='f'*64
    if case=='policy': m['policy_version']='unreviewed'
    if case=='wrong_event': e['event_id']='123'
    if case=='wrong_url': e['sources'][1]['url']='https://evil.example/'
    if case=='future_receipt': e['sources'][1]['observed_at']='2026-10-01T00:00:00Z'
    if case=='activity': e['offensive_activity'][0]['yards']=69
    if case=='boolean_stat': m['supplemented_fields']['receptions']=False
    if case=='missing_source': e['sources']=[]
    if case=='malformed_sources': e['sources']=[None,None]
    m['explicit_source_sha256']=_sha(e);item['source_sha256']=_sha(m)
    assert not valid(row,item)
