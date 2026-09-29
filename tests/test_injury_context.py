from datetime import date

import pytest

from sportsbet.prop.injury_context import (_nba_split, _nfl_split, current_contexts,
    relevant_availability_reports)


def test_contexts_require_relevant_unit_and_exact_nfl_identity():
    context={'status':'observed','pfr_player_identities':{'1':'ReceDa00','2':'DefeDa00'},'teams':[
        {'abbreviation':'NE','roster_ids':{'1':'Receiver','9':'Target'},'reports':[
            {'player':'Receiver','position':'WR','status':'Out'},
            {'player':'Guard','position':'G','status':'Active'},
            {'player':'Corner teammate','position':'CB','status':'Out'}]},
        {'abbreviation':'NYJ','roster_ids':{'2':'Defender','3':'Other'},'reports':[
            {'player':'Defender','position':'CB','status':'Questionable'},
            {'player':'Other','position':'WR','status':'Out'}]}]}
    rows=current_contexts(context,'NE','Target','nfl')
    assert [(row['player'],row['relationship'],row['unit'],row['participant_id']) for row in rows]==[
        ('Receiver','teammate','offense','ReceDa00'),
        ('Defender','opponent','defense','DefeDa00')]


def test_relevant_reports_exclude_same_team_defense_and_opponent_offense_without_requiring_crosswalk():
    context={'status':'observed','teams':[
        {'abbreviation':'NE','reports':[
            {'player':'Receiver','position':'WR','status':'Out','reported_at':'2026-09-20T00:00:00Z'},
            {'player':'Corner teammate','position':'CB','status':'Out','reported_at':'2026-09-20T00:00:00Z'}]},
        {'abbreviation':'NYJ','reports':[
            {'player':'Defender','position':'CB','status':'Questionable','reported_at':'2026-09-20T00:00:00Z'},
            {'player':'Quarterback','position':'QB','status':'Out','reported_at':'2026-09-20T00:00:00Z'}]}]}
    rows=relevant_availability_reports(context,'NE','Target','nfl')
    assert [(row['player'],row['relationship'],row['unit']) for row in rows]==[
        ('Receiver','teammate','offense'),('Defender','opponent','defense')]


def test_nba_reports_treat_teammates_and_opponents_as_relevant_lineup_context():
    context={'status':'observed','teams':[
        {'abbreviation':'BOS','reports':[{'player':'Guard','position':'PG','status':'Out'}]},
        {'abbreviation':'NY','reports':[{'player':'Center','position':'C','status':'Questionable'}]}]}
    rows=relevant_availability_reports(context,'BOS','Target','nba')
    assert [(row['player'],row['relationship'],row['unit']) for row in rows]==[
        ('Guard','teammate','offense'),('Center','opponent','defense')]


@pytest.mark.asyncio
async def test_nfl_split_requires_tenure_source_coverage_and_strips_internal_id():
    class Connection:
        async def fetchrow(self,sql,*args):
            self.sql,self.args=sql,args
            return {'active_games':8,'active_mean':241.25,'active_hits':5,
                    'absent_games':0,'absent_mean':None,'absent_hits':0,'unknown_games':2}
    conn=Connection()
    result=await _nfl_split(conn,'target',2024,date(2026,9,20),'pass_yds',225.5,'over',
        {'player':'Defender','status':'Out','position':'CB','team':'WSH','stat_team':'WAS',
         'relationship':'opponent','unit':'defense','participant_id':'DefeDa00'})
    assert 'MIN(season*100+week)' in conn.sql and 'CASE WHEN COUNT(*)=1' in conn.sql
    assert 'defense_snaps>0' in conn.sql and conn.args[-2:]==('WAS','DefeDa00')
    assert result['active']=={'games':8,'mean':241.25,'hit_rate':.625}
    assert result['absent']=={'games':0,'mean':None,'hit_rate':None}
    assert result['unknown_games']==2 and result['evidence_version']=='recorded-participation-v2'
    assert 'participant_id' not in result and result['team']=='WSH'


@pytest.mark.asyncio
async def test_nba_split_uses_canonical_team_and_integer_subject_identity():
    class Connection:
        async def fetch(self,sql,*args):
            assert args==('Injured Teammate','LAC')
            return [{'player_id':321}]
        async def fetchrow(self,sql,*args):
            self.sql,self.args=sql,args
            return {'active_games':10,'active_mean':25,'active_hits':7,
                    'absent_games':5,'absent_mean':29,'absent_hits':4,'unknown_games':3}
    conn=Connection()
    result=await _nba_split(conn,'123',2024,date(2026,9,20),'points',22.5,'over',
        {'player':'Injured Teammate','status':'Out','position':'SG','team':'LA',
         'stat_team':'LAC','relationship':'teammate','unit':'offense'})
    assert conn.args[0] == 123 and conn.args[-2:] == ('LAC',321)
    assert result['absent']=={'games':5,'mean':29.0,'hit_rate':.8}
    assert 'stat_team' not in result

@pytest.mark.asyncio
@pytest.mark.parametrize('split,prop', [(_nfl_split,'pass_yds'),(_nfl_split,'rush_yds'),(_nfl_split,'receptions'),(_nba_split,'points')])
async def test_context_rejects_naive_observation_cutoff_before_query(split,prop):
    from datetime import datetime
    with pytest.raises(ValueError,match='aware timestamp'):
        await split(None,'123',2024,date(2026,9,30),prop,1.5,'over',{},datetime(2026,9,29))


@pytest.mark.asyncio
async def test_public_context_dispatch_passes_observation_cutoff_to_nba(monkeypatch):
    from datetime import datetime,timezone
    from sportsbet.prop import injury_context as context_module
    now=datetime(2026,9,29,tzinfo=timezone.utc);candidate={'player':'Fixture'}
    monkeypatch.setattr(context_module,'current_contexts',lambda *args:[candidate])
    class Lease:
        async def __aenter__(self):return 'connection'
        async def __aexit__(self,*args):pass
    class Pool:
        def acquire(self):return Lease()
    async def split(*args):
        assert args[-1]==now and args[-2] is candidate
        return {'active':{'games':1}}
    monkeypatch.setattr(context_module,'_nba_split',split)
    result=await context_module.historical_availability_splits(Pool(),context={},subject_team='BOS',subject_player='Target',sport='nba',player_id='123',season=2024,cutoff=date(2026,9,30),prop_type='points',line=1.5,direction='over',observed_before=now)
    assert result==[{'active':{'games':1}}]

@pytest.mark.parametrize('change',[
    {'active_oldest':None}, {'active_oldest':date(2026,9,5)},
    {'active_newest':date(2026,9,30)}, {'unknown_oldest':date(2026,9,1)},
])
def test_context_sample_window_rejects_missing_reversed_future_or_empty_group_dates(change):
    from sportsbet.prop.injury_context import _sample_window
    row=dict(active_games=2,active_oldest=date(2026,9,1),active_newest=date(2026,9,4),absent_games=0,unknown_games=0)
    assert _sample_window(row|change,date(2026,9,30)) is None


def test_context_sample_window_keeps_groups_separate_and_empty_groups_explicit():
    from sportsbet.prop.injury_context import _sample_window
    row=dict(active_games=2,active_oldest=date(2025,9,1),active_newest=date(2025,9,8),
        absent_games=1,absent_oldest=date(2026,9,1),absent_newest=date(2026,9,1),unknown_games=0)
    assert _sample_window(row,date(2026,9,30))==dict(cutoff='2026-09-30',
        active=dict(oldest='2025-09-01',newest='2025-09-08'),
        absent=dict(oldest='2026-09-01',newest='2026-09-01'),unknown=None)


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('mapped_ids',[['1'],['2'],['1','2']])
def test_nfl_context_never_selects_one_of_two_roster_ids_with_the_same_name(reverse,mapped_ids):
    entries=[('1','Receiver'),('2','Receiver'),('9','Target'),('3','Unique Receiver')]
    if reverse:entries.reverse()
    context={'status':'observed','pfr_player_identities':{
        **{identity:'Part'+identity for identity in mapped_ids},'3':'Unique00'},'teams':[
        {'abbreviation':'NE','roster_ids':dict(entries),'reports':[
            {'player':'Receiver','position':'WR','status':'Out'},
            {'player':'Unique Receiver','position':'TE','status':'Questionable'}]}]}
    rows=current_contexts(context,'NE','Target','nfl')
    assert [(row['player'],row['participant_id']) for row in rows]==[('Unique Receiver','Unique00')]
    # An uncertain history binding must not suppress the current injury warning
    # or loosen the existing baseline qualification gate.
    from sportsbet.prop.availability import blocks_unadjusted_teammate_context
    reports=relevant_availability_reports(context,'NE','Target','nfl')
    ambiguous=next(row for row in reports if row['player']=='Receiver')
    assert blocks_unadjusted_teammate_context(ambiguous)


@pytest.mark.asyncio
async def test_ambiguous_nfl_context_is_rejected_before_history_queries():
    from sportsbet.prop.injury_context import historical_availability_splits
    context={'status':'observed','pfr_player_identities':{'1':'First00','2':'Second00'},'teams':[
        {'abbreviation':'NYJ','roster_ids':{'1':'Defender','2':'Defender'},'reports':[
            {'player':'Defender','position':'CB','status':'Out'}]}]}
    class Pool:
        def acquire(self):raise AssertionError('Ambiguous participant must not reach SQL')
    rows=await historical_availability_splits(Pool(),context=context,subject_team='NE',
        subject_player='Target',sport='nfl',player_id='00-0000001',season=2024,
        cutoff=date(2026,9,30),prop_type='pass_yds',line=200.5,direction='over')
    assert rows==[]
