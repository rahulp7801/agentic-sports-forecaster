import test from 'node:test';
import assert from 'node:assert/strict';
import {forecastPage,forecastRequest} from '../lib/forecastPage.ts';
import {FORECAST_DISPLAY_PROTOCOL,readForecastDisplayAuthority,currentLiveForecastRows} from '../lib/forecastDisplayAuthority.ts';

const now=Date.parse('2026-09-30T12:00:00Z'),stamp=new Date(now).toISOString();
const base={id:'A',player:'Player A',team:'KC',opponent:'BUF',sport:'nfl',home_team:'KC',away_team:'BUF',game_id:'game',
  prop_type:'pass_yds',line:249.5,direction:'over',true_prob:.6,american_odds:100,push_probability:0,
  sportsbook:'draftkings',model_version:'empirical-jeffreys-v4-nfl-history-v1',history_policy_version:'nfl-explicit-receiving-v1',
  sample_size:40,mean_stat:260,confidence_interval:[.55,.65],kelly_fraction:.01,gated:false,
  forecast_cutoff:'2026-09-30',trade_plan:[],injury_flags:{},market_type:'player_pass_yds',
  snapped_at:stamp,history_observed_before:stamp,captured_at:stamp,game_start_time:new Date(now+2*3600000).toISOString(),
  availability:{status:'observed',roster_confirmed:true,subject_status:'Not listed on injury report',probability_adjusted:false,
    captured_at:stamp,team:'KC',teammates:[],source_url:'https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries',
    source_sha256:'a'.repeat(64),roster_source_url:'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/12/roster',roster_source_sha256:'b'.repeat(64)}};
const revision='a'.repeat(64);
function page(values,view='qualified',patch={},clock=now) {
  const input={rows:values.map(signal=>({payload:{generated_at:stamp,games:[],signals:[signal]}})),profiles:{},
    total_count:values.length,revision,metadata:{generated_at:stamp,signals:[],games:[]},invalid_envelopes:0,window_complete:true,...patch};
  return forecastPage(input,forecastRequest(new URL('https://example.test/api/signals?sport=nfl&view='+view)),clock);
}
const binding=(result,view='qualified')=>({revision:result.pagination.revision,view,
  complete:result.pagination.complete,invalid_signals:result.invalid_signals});
const live=(result,clock=now,view='qualified')=>currentLiveForecastRows(result.display,result.signals,binding(result,view),clock);
const read=(result,view='qualified')=>readForecastDisplayAuthority(result.display,result.signals,binding(result,view));

test('server page issues ordered classification and deadline metadata without changing the selected metrics',()=>{
  const result=page([base,{...base,id:'ALT',line:250.5},{...base,id:'STRONG',player:'Player B',confidence_interval:[.58,.65]}]);
  assert.deepEqual(result.signals.map(row=>row.id),['STRONG','A','ALT']);
  assert.equal(result.display.protocol,FORECAST_DISPLAY_PROTOCOL);assert.equal(result.display.revision,revision);
  assert.deepEqual(result.display.rows.map(row=>[row.id,row.role,row.primary_index,row.group_rank]),
    [['STRONG','primary',0,0],['A','primary',1,1],['ALT','alternative',1,1]]);
  for(const signal of result.signals) {assert.equal(signal.true_prob,.6);assert.ok(Math.abs(signal.expected_return-.2)<1e-12);}
  assert.equal(result.display.rows[0].actionable_until,new Date(now+300001).toISOString());
  assert.equal(result.display.rows[0].lock_at,new Date(now+3600000).toISOString());
  assert.deepEqual(live(result).map(row=>row.id),['STRONG','A','ALT']);
  assert.equal(live(result,now+300000).length,3);
  assert.deepEqual(live(result,now+300001),[]);
});

test('the earliest source deadline is issued by the private producer and enforced at the exact boundary',()=>{
  for(const [patch,remaining] of [
    [{snapped_at:new Date(now-299000).toISOString()},1001],
    [{availability:{...base.availability,captured_at:new Date(now-3599000).toISOString()}},1001],
    [{game_start_time:new Date(now+3601000).toISOString()},1000]]) {
    const result=page([{...base,...patch}]);
    assert.equal(result.signals.length,1);assert.equal(result.display.rows[0].actionable_until,new Date(now+remaining).toISOString());
    assert.equal(live(result,now+remaining-1).length,1);
    assert.deepEqual(live(result,now+remaining),[]);
  }
});

test('an expired primary withholds its alternatives instead of promoting a fresh alternate',()=>{
  const result=page([{...base,snapped_at:new Date(now-299000).toISOString()},
    {...base,id:'ALT',line:250.5,confidence_interval:[.54,.65]},
    {...base,id:'OTHER',player:'Other Player',confidence_interval:[.52,.68]}]);
  assert.equal(result.display.rows[1].role,'alternative');
  assert.ok(Date.parse(result.display.rows[1].actionable_until)>now+1001);
  assert.equal(live(result,now+1000).length,3);
  assert.deepEqual(live(result,now+1001).map(row=>[row.id,row.group_rank]),[['OTHER',1]]);
});

test('stale watchlist and archived research stay descriptive and never become live approval',()=>{
  const watch=page([{...base,snapped_at:new Date(now-6*60000).toISOString()}],'candidates');
  assert.equal(watch.signals[0].gate_reason,'stale_quote');assert.equal(watch.display.rows[0].state,'watchlist');
  assert.equal(watch.display.rows[0].actionable_until,null);assert.equal(watch.display.rows[0].visible_until,watch.display.rows[0].lock_at);
  assert.ok(read(watch,'candidates'));
  assert.deepEqual(live(watch,now,'candidates'),[]);
  const research=page([base],'library');assert.equal(research.display.rows[0].state,'research');
  assert.equal(research.display.rows[0].visible_until,null);
  assert.deepEqual(live(research,now,'library'),[]);
  assert.deepEqual(live(research,now+86400000,'library'),[]);
});

test('missing gate flags, unknown state, mismatched IDs, ranks or reasons cannot become approval',()=>{
  const result=page([base]);
  for(const mutate of [
    v=>{delete v.signals[0].gated;},v=>{v.signals[0].gated='false';},
    v=>{v.display.rows[0].state='unknown';},v=>{v.display.rows[0].id='other';},
    v=>{v.display.rows[0].group_rank=2;},v=>{v.display.rows[0].gate_reason='private reason';},
    v=>{v.display.rows[0].actionable_until=new Date(now+7200000).toISOString();}]) {
    const value=structuredClone(result);mutate(value);
    assert.equal(read(value),null);
    assert.deepEqual(live(value),[]);
  }
  const held=structuredClone(result);held.signals[0].gated=true;held.signals[0].gate_reason='risk_gate';
  held.signals[0].true_prob=.99;held.signals[0].expected_return=100;
  held.display.rows[0].gated=true;held.display.rows[0].gate_reason='risk_gate';
  assert.deepEqual(live(held),[]);
});

test('incomplete or invalid coverage and an untrusted clock withhold live actions',()=>{
  const incomplete=page([base],'qualified',{total_count:5002});
  assert.deepEqual(incomplete.signals,[]);assert.equal(incomplete.display.complete,false);
  const result=page([base]);
  for(const patch of [{complete:false},{invalid_signals:1},{complete:'true'}])
    assert.deepEqual(live({...result,display:{...result.display,...patch}}),[]);
  for(const clock of [NaN,Infinity,now-1,now+.5]) assert.deepEqual(live(result,clock),[]);
  const withPrivate=structuredClone(result.display);withPrivate.raw_evidence='never copied';withPrivate.rows[0].parameters='never copied';
  const projected=read({...result,display:withPrivate});
  assert.equal(JSON.stringify(projected).includes('never copied'),false);
});

test('authority cannot be combined with another page revision, view or coverage',()=>{
  const result=page([base]);
  for(const patch of [{revision:'b'.repeat(64)},{view:'library'},{complete:false},{invalid_signals:1}]) {
    const context={...binding(result),...patch};
    assert.equal(readForecastDisplayAuthority(result.display,result.signals,context),null);
    assert.deepEqual(currentLiveForecastRows(result.display,result.signals,context,now),[]);
  }
});

test('display metadata remains inside the transport byte limit and continuation preserves every source row',()=>{
  const teammate={player:'🏈'.repeat(13),status:'Active',position:'WR',reported_at:stamp};
  const values=Array.from({length:100},(_,index)=>({...base,id:String(index),
    availability:{...base.availability,teammates:Array(64).fill(teammate)}}));
  const first=page(values,'library');
  assert.ok(first.signals.length>0&&first.signals.length<100);
  assert.ok(Buffer.byteLength(JSON.stringify(first))<1024*1024-2048);
  assert.equal(first.pagination.complete,false);assert.equal(first.pagination.next_offset,first.signals.length);
  const offset=first.pagination.next_offset;
  const rest=forecastPage({rows:values.slice(offset).map(signal=>({payload:{generated_at:stamp,games:[],signals:[signal]}})),
    profiles:{},total_count:100,revision,metadata:{generated_at:stamp,signals:[],games:[]},invalid_envelopes:0,window_complete:true},
    forecastRequest(new URL('https://example.test/api/signals?sport=nfl&offset='+offset)),now);
  assert.equal(rest.pagination.complete,true);
  assert.deepEqual([...first.signals,...rest.signals].map(signal=>signal.id),values.map(signal=>signal.id));
});
