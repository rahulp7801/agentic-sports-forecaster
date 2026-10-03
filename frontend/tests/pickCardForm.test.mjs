import test from 'node:test';
import assert from 'node:assert/strict';
import {pickCardFormRequest,pickCardFormSnapshot,pickCardFormSummary} from '../lib/pickCardForm.ts';

const signal={id:'p1',player:'Receiver',player_id:'00-0000001',sport:'nfl',
  forecast_cutoff:'2026-09-17',snapped_at:'2026-09-17T01:00:00Z',
  captured_at:'2026-09-17T01:01:00Z',game_start_time:'2026-09-18T00:00:00Z',
  prop_type:'receptions',line:4.5,direction:'over',
  availability:{status:'observed',roster_confirmed:true,team:'BUF',captured_at:'2026-09-17T01:00:00Z'}};
const row=(date,receptions,team='BUF',player_id=signal.player_id)=>({
  date,player:'Receiver',player_id,team,opponent:'DET',receptions});

test('card fetch uses exact identity, pregame source receipt and target-date cutoff',()=>{
  const url=pickCardFormRequest(signal);
  assert.ok(url);
  const query=new URL(url,'https://example.test').searchParams;
  assert.equal(query.get('player_id'),signal.player_id);
  assert.equal(query.get('before'),'2026-09-17');
  assert.equal(query.get('observed_before'),signal.captured_at);
  assert.equal(query.get('exact'),'1');
  assert.equal(pickCardFormRequest({...signal,player_id:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,availability:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,captured_at:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,captured_at:signal.game_start_time}),null);
  assert.equal(pickCardFormRequest({...signal,availability:{...signal.availability,
    captured_at:'2026-09-17T01:02:00Z'}}),null);
});

test('card summarizes only captured-team games in the last 30 days',()=>{
  const rows=[row('2026-09-15',6),row('2026-09-14',2),row('2026-09-13',10,'KC'),
    row('2026-08-01',90),row('2026-09-15',99,'BUF','00-0000002')];
  const summary=pickCardFormSummary(rows,signal);
  assert.match(summary,/BUF last 30 days: 2 recorded stats in 2 games, average 4.0/);
  assert.match(summary,/Latest 2026-09-15, 2 days before the target game/);
  assert.doesNotMatch(summary,/does not establish current form/);
  assert.doesNotMatch(summary,/90|99/);
  assert.match(pickCardFormSummary([row('2026-09-15',3,'KC')],signal),/No BUF game appears in the retrieved records/);
  assert.match(pickCardFormSummary([row('2026-09-15',undefined)],signal),/stat was unavailable/);
});

test('card shows recorded form for NFL roster and stat-feed team aliases',()=>{
  for(const [roster,stat] of [['LAR','LA'],['WSH','WAS']]) {
    const captured={...signal,availability:{...signal.availability,team:roster}};
    const summary=pickCardFormSummary([row('2026-09-15',6,stat)],captured);
    assert.match(summary,new RegExp(`${roster} last 30 days: 1 recorded stat in 1 game, average 6.0`));
    assert.doesNotMatch(summary,/No .* game appears/);
  }
});

test('NBA card shows captured-team form when ESPN and NBA codes differ',()=>{
  for(const [roster,stat] of [['GS','GSW'],['NY','NYK'],['UTAH','UTA']]) {
    const nba={...signal,sport:'nba',player_id:'123',prop_type:'points',line:20.5,
      availability:{...signal.availability,team:roster}};
    const summary=pickCardFormSummary([{date:'2026-09-15',player:'Receiver',
      player_id:'123',team:stat,opponent:'BOS',points:25}],nba);
    assert.match(summary,new RegExp(roster+' last 30 days: 1 recorded stat in 1 game, average 25.0'));
    assert.doesNotMatch(summary,/No .* game appears/);
  }
});

test('older 30-day observations disclose their age instead of implying current form',()=>{
  const older=pickCardFormSummary([row('2026-08-25',6)],signal);
  assert.match(older,/Latest 2026-08-25, 23 days before the target game/);
  assert.match(older,/does not establish current form/);
  const missing=pickCardFormSummary([row('2026-08-25',undefined)],signal);
  assert.match(missing,/stat was unavailable/);
  assert.match(missing,/23 days before the target game/);
  assert.doesNotMatch(pickCardFormSummary([row('2026-09-03',6)],signal),/does not establish current form/);
  assert.match(pickCardFormSummary([row('2026-09-02',6)],signal),/does not establish current form/);
});

test('the stable card snapshot retains the pregame times required by form validation',()=>{
  const snapshot=pickCardFormSnapshot(signal);
  assert.equal(snapshot.captured_at,signal.captured_at);
  assert.equal(snapshot.game_start_time,signal.game_start_time);
  assert.equal(snapshot.availability.captured_at,signal.availability.captured_at);
  assert.match(pickCardFormSummary([row('2026-09-16',6)],snapshot),
    /BUF last 30 days: 1 recorded stat in 1 game, average 6.0/);
  assert.throws(()=>pickCardFormSummary([row('2026-09-16',6)],
    pickCardFormSnapshot({...signal,captured_at:undefined})));
});

test('new NBA card requests game logs as of model selection, not later write',()=>{
  const nba={...signal,player_id:'123',sport:'nba',prop_type:'points',line:22.5,
    model_version:'empirical-jeffreys-v4-nba-source-asof-v1',
    history_policy_version:'nba-source-asof-v1',
    snapped_at:'2026-10-04T03:00:00Z',history_observed_before:'2026-10-04T03:00:10Z',
    captured_at:'2026-10-04T03:01:00Z',game_start_time:'2026-10-04T08:00:00Z',
    forecast_cutoff:'2026-10-04',availability:{...signal.availability,
      captured_at:'2026-10-04T03:00:00Z',team:'BOS'}};
  const snapshot=pickCardFormSnapshot(nba);
  assert.equal(snapshot.history_observed_before,nba.history_observed_before);
  assert.equal(snapshot.model_version,nba.model_version);
  const request=pickCardFormRequest(snapshot);
  assert.equal(new URL(request,'https://example.test').searchParams.get('observed_before'),
    nba.history_observed_before);
  assert.equal(pickCardFormRequest({...nba,history_observed_before:undefined}),null);
  assert.notEqual(new URL(request,'https://example.test').searchParams.get('observed_before'),
    nba.captured_at);
});

test('new football cards request the retained pre-inference source cutoff',()=>{
  for(const [sport,version,policy,id] of [
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001'],
    ['cfb','empirical-jeffreys-v4-cfb-history-v1','cfb-explicit-receiving-v1','123']]) {
    const football={...signal,sport,player_id:id,model_version:version,
      history_policy_version:policy,history_observed_before:'2026-10-04T03:00:10Z',
      snapped_at:'2026-10-04T03:00:00Z',captured_at:'2026-10-04T03:01:00Z',
      game_start_time:'2026-10-04T08:00:00Z',forecast_cutoff:'2026-10-04',
      availability:{...signal.availability,captured_at:'2026-10-04T03:00:00Z'}};
    const request=pickCardFormRequest(pickCardFormSnapshot(football));
    assert.equal(new URL(request,'https://example.test').searchParams.get('observed_before'),
      football.history_observed_before);
    assert.equal(pickCardFormRequest({...football,history_observed_before:undefined}),null);
    const older=pickCardFormRequest({...football,model_version:'empirical-jeffreys-v4',
      history_policy_version:undefined,history_observed_before:undefined});
    assert.equal(new URL(older,'https://example.test').searchParams.get('observed_before'),
      football.captured_at);
  }
});

test('invalid or unverified context cannot become a card form claim',()=>{
  assert.match(pickCardFormSummary([row('2026-09-15',6)],{...signal,availability:undefined}),/not verified/);
  assert.match(pickCardFormSummary([row('2026-09-17',9)],signal),/No BUF game appears in the retrieved records/);
  assert.throws(()=>pickCardFormSummary([row('2026-09-15',9,'BUF','bad-id')],signal));
});

test('a full display window declares that earlier games may be missing',()=>{
  const rows=Array.from({length:20},(_,index)=>row(
    new Date(Date.parse('2026-09-15')-index*86400000).toISOString().slice(0,10),index));
  assert.match(pickCardFormSummary(rows,signal),/Only the latest 20 records were checked/);
});
