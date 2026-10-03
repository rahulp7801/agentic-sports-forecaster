"""Minutes commitments are independent of frozen NBA result hashes."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from sportsbet.ingestion.nba_participation import (
    minute_value, participation_record, prepare_participation,
)
from sportsbet.ingestion.provenance import row_sha256, stat_row_sha256
from sportsbet.prop.nba_participation_evidence import nba_participation_split, verified_participant

NOW=datetime(2026,10,8,tzinfo=timezone.utc)
CANDIDATE=dict(player='Injured Teammate',status='Out',position='SG',team='LA',
    stat_team='LAC',relationship='teammate',unit='offense')


def source_row(**changes):
    row=dict(player_id=321,player_name='Injured Teammate',game_id='0022500001',
        game_date=date(2026,1,1),season=2025,team_abbreviation='LAC',minutes=20,
        points=10,rebounds=2,assists=3,source_provider='nba',source_sha256='a'*64,
        source_observed_at=NOW-timedelta(days=1))|changes
    row['source_record_sha256']=stat_row_sha256('nba',row)
    return row


def receipt(row,version=1):
    return prepare_participation([row])[0]|dict(version_id=version,recorded_at=NOW)


def test_minutes_corrections_leave_frozen_stat_hash_unchanged_but_change_minutes_proof():
    original=source_row();corrected=source_row(minutes=0)
    assert original['source_record_sha256']==corrected['source_record_sha256']
    first,second=prepare_participation([original])[0],prepare_participation([corrected])[0]
    assert first['source_record_sha256']!=second['source_record_sha256']
    assert first['source_sha256']!=second['source_sha256']
    assert first['stat_record_sha256']==second['stat_record_sha256']
    assert row_sha256(participation_record(first))==first['source_record_sha256']


@pytest.mark.parametrize('value,expected',[(20.15,20.2),(Decimal('20.05'),20.1),(0,0.),(None,None),(float('nan'),None)])
def test_minutes_commit_the_value_retained_by_postgres(value,expected):
    assert minute_value(value)==expected
    row=receipt(source_row(minutes=value))
    assert verified_participant(row,NOW)['minutes']==expected


@pytest.mark.parametrize('value',[True,'20',-1,float('inf'),1000,Decimal('NaN')])
def test_invalid_minutes_cannot_become_proof(value):
    with pytest.raises(ValueError):prepare_participation([source_row(minutes=value)])


@pytest.mark.parametrize('change',[
    {'minutes':0},{'player_name':'Someone Else'},{'team_abbreviation':'BOS'},
    {'recorded_at':NOW+timedelta(seconds=1)},
    {'source_observed_at':NOW+timedelta(seconds=1)}, {'source_sha256':'bad'},
])
def test_receipt_damage_or_late_receipt_is_rejected(change):
    with pytest.raises(ValueError):verified_participant(receipt(source_row())|change,NOW)


def test_source_scope_and_batch_duplicates_fail_closed():
    with pytest.raises(ValueError,match='Duplicate'):prepare_participation([source_row(),source_row()])
    with pytest.raises(ValueError):prepare_participation([source_row(season=2026)])
    with pytest.raises(ValueError):prepare_participation([source_row(source_provider='unknown')])
    raw=source_row(source_provider='espn',source_sha256='c'*64)
    assert prepare_participation([raw])[0]['source_sha256']=='c'*64


class EvidenceConnection:
    def __init__(self,identities=None,rows=None):
        self.identities=identities if identities is not None else [receipt(source_row())]
        target=source_row(player_id=123,player_name='Target')
        self.rows=rows if rows is not None else [dict(subject=target,participant=receipt(source_row()))]
        self.calls=[]
    async def fetchval(self,sql):return NOW
    async def fetch(self,sql,*args):
        self.calls.append((sql,args))
        return self.identities if len(self.calls)==1 else self.rows


@pytest.mark.asyncio
@pytest.mark.parametrize('participant,active,absent,unknown',[
    (receipt(source_row()),1,0,0), (receipt(source_row(minutes=0)),0,0,0),
    (None,0,0,1), ('null',0,0,1),
    (receipt(source_row())|{'minutes':0},0,0,1),
    (receipt(source_row(minutes=None)),0,0,1),
])
async def test_only_verified_minutes_classify_participation(participant,active,absent,unknown):
    # Positive tenure is independently established by the same participant in a
    # prior game. A proved zero must not be mistaken for missing participation.
    target=source_row(player_id=123,player_name='Target',game_date=date(2026,1,2))
    if isinstance(participant,dict):
        minute=participant['minutes']
        valid=row_sha256(participation_record(participant))==participant['source_record_sha256']
        participant=receipt(source_row(game_date=date(2026,1,2),minutes=minute)) if valid else participant
    conn=EvidenceConnection(rows=[dict(subject=target,participant=participant)])
    result=await nba_participation_split(conn,'123',2024,date(2026,9,20),'points',5.5,'over',CANDIDATE,NOW)
    if isinstance(participant,dict) and participant['minutes']==0 and unknown==0:absent=1
    assert result['active']['games']==active and result['absent']['games']==absent
    assert result['unknown_games']==unknown
    assert result['evidence_version']=='recorded-participation-v3'
    assert 'source_rows' in result and 'stat_team' not in result
    assert result['identity_refs'][0]['version_id']==1


@pytest.mark.asyncio
async def test_bad_target_commitment_and_ambiguous_identity_withhold_comparison():
    target=source_row(player_id=123,points=999)|{'source_record_sha256':'b'*64}
    conn=EvidenceConnection(rows=[dict(subject=target,participant=None)])
    assert await nba_participation_split(conn,123,2024,date(2026,9,20),'points',5.5,'over',CANDIDATE,NOW) is None
    conn=EvidenceConnection(identities=[receipt(source_row()),receipt(source_row(player_id=322))])
    assert await nba_participation_split(conn,123,2024,date(2026,9,20),'points',5.5,'over',CANDIDATE,NOW) is None


@pytest.mark.asyncio
async def test_proved_recent_nba_zero_minutes_and_unknowns_stay_distinct_from_old_history():
    def pair(game,day,points,minutes):
        target=source_row(player_id=123,player_name='Target',game_id=game,game_date=day,points=points)
        participant=receipt(source_row(game_id=game,game_date=day,minutes=minutes)) if minutes is not None else None
        return dict(subject=target,participant=participant)
    old=pair('old',date(2026,1,1),100,20)
    active=pair('active',date(2026,3,8),10,20)
    absent=pair('absent',date(2026,4,1),30,0)
    unknown=pair('unknown',date(2026,4,6),99,None)
    conn=EvidenceConnection(rows=[old,active,absent,unknown])
    result=await nba_participation_split(conn,'123',2024,date(2026,4,7),'points',20,'over',CANDIDATE,NOW)
    assert result['active']==dict(games=2,mean=55.,hit_rate=.5)
    recent=result['recent_window']
    assert recent['since']=='2026-03-08'
    assert recent['active']==dict(games=1,mean=10.,hit_rate=0.)
    assert recent['absent']==dict(games=1,mean=30.,hit_rate=1.)
    assert recent['unknown_games']==1
