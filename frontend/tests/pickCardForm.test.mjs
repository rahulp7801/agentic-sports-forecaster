import test from 'node:test';
import assert from 'node:assert/strict';
import {pickCardFormRequest,pickCardFormSummary} from '../lib/pickCardForm.ts';

const signal={id:'p1',player:'Receiver',player_id:'00-0000001',sport:'nfl',
  forecast_cutoff:'2026-09-17',snapped_at:'2026-09-17T01:00:00Z',
  captured_at:'2026-09-17T01:01:00Z',game_start_time:'2026-09-18T00:00:00Z',
  prop_type:'receptions',line:4.5,direction:'over',
  availability:{status:'observed',roster_confirmed:true,team:'BUF'}};
const row=(date,receptions,team='BUF',player_id=signal.player_id)=>({
  date,player:'Receiver',player_id,team,opponent:'DET',receptions});

test('card fetch uses exact identity, pregame observation and overnight cutoffs',()=>{
  const url=pickCardFormRequest(signal);
  assert.ok(url);
  const query=new URL(url,'https://example.test').searchParams;
  assert.equal(query.get('player_id'),signal.player_id);
  assert.equal(query.get('before'),'2026-09-16');
  assert.equal(query.get('observed_before'),signal.captured_at);
  assert.equal(query.get('exact'),'1');
  assert.equal(pickCardFormRequest({...signal,player_id:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,availability:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,captured_at:undefined}),null);
  assert.equal(pickCardFormRequest({...signal,captured_at:signal.game_start_time}),null);
});

test('card summarizes only captured-team games in the last 30 days',()=>{
  const rows=[row('2026-09-15',6),row('2026-09-14',2),row('2026-09-13',10,'KC'),
    row('2026-08-01',90),row('2026-09-15',99,'BUF','00-0000002')];
  const summary=pickCardFormSummary(rows,signal);
  assert.match(summary,/BUF last 30 days: 2 recorded stats in 2 games, average 4.0/);
  assert.match(summary,/Latest 2026-09-15/);
  assert.doesNotMatch(summary,/90|99/);
  assert.match(pickCardFormSummary([row('2026-09-15',3,'KC')],signal),/No BUF game appears in the retrieved records/);
  assert.match(pickCardFormSummary([row('2026-09-15',undefined)],signal),/stat was unavailable/);
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
