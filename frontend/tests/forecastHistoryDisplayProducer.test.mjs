import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {forecastHistoryDisplay} from '../lib/forecastHistoryDisplayProducer.ts';
import {forecastHistory,recentForm,calendarForm} from '../lib/forecastHistory.ts';
import {pickCardFormSummary} from '../lib/pickCardForm.ts';
import {readSignalDisplay} from '../lib/signalDisplay.ts';
import {canonicalForecastDisplayJson} from '../lib/forecastDisplayPacket.ts';
import {readForecastHistoryDisplay} from '../lib/forecastHistoryDisplay.ts';
import {contextWindowText,recentParticipationText} from '../lib/participationDisplay.ts';

const revision='a'.repeat(64),stamp='2026-10-14T01:00:00Z',selected='2026-10-14T01:00:10Z',captured='2026-10-14T01:01:00Z';
const base={id:'forecast-1',player:'Player',player_id:'00-0000001',team:'BUF',opponent:'DET',home_team:'Home',away_team:'Away',game_id:'game',
  sport:'nfl',prop_type:'receptions',line:4,direction:'under',true_prob:.6,implied_prob:.5,ev_pct:.1,expected_return:.2,
  push_probability:0,confidence_interval:[.55,.7],model_version:'empirical-jeffreys-v4-nfl-history-v1',
  history_policy_version:'nfl-explicit-receiving-v1',history_observed_before:selected,forecast_cutoff:'2026-10-14',
  snapped_at:stamp,captured_at:captured,game_start_time:'2026-10-15T00:00:00Z',kelly_fraction:.01,
  american_odds:100,sportsbook:'draftkings',trade_plan:[],injury_flags:{},market_type:'player_receptions',strength:'unrated',
  gated:false,sample_size:40,mean_stat:5,availability:{status:'observed',roster_confirmed:true,subject_status:'Active',
    probability_adjusted:false,captured_at:stamp,team:'BUF',teammates:[],source_url:'https://example.test/injuries',
    source_sha256:'a'.repeat(64),roster_source_url:'https://example.test/roster',roster_source_sha256:'b'.repeat(64)}};
const row=(date,receptions,patch={})=>({date,player:'Player',player_id:base.player_id,team:'BUF',opponent:'DET',receptions,...patch});
const source=(logs,patch={})=>({logs,game_date_before:base.forecast_cutoff,source_observed_before:selected,...patch});
const binding=result=>({revision:result.revision,subject:result.subject,scope:result.scope});

test('private producer preserves exact existing history/form/card calculations and the full public record commitment',()=>{
  const logs=[row('2026-10-14',99),row('2026-10-13',undefined),row('2026-10-12',0),row('2026-10-11',4),
    row('2026-10-10',8),row('2026-10-09',3),row('2026-10-08',2),row('2026-09-01',40),
    row('2026-10-12',99,{player_id:'00-0000002'})];
  const before=structuredClone({base,logs}),result=forecastHistoryDisplay(base,revision,source(logs));
  assert.equal(result.status,'available');assert.equal(result.source_coverage,'bounded_as_of_records');
  assert.deepEqual(result.windows['10'],forecastHistory(logs,base,10));
  assert.deepEqual(result.windows['20'],forecastHistory(logs,base,20));
  assert.deepEqual(result.recent,recentForm(logs,base));assert.deepEqual(result.calendar,calendarForm(logs,base));
  assert.equal(result.card_summary,pickCardFormSummary(logs,base));
  assert.equal(result.subject.forecast_record_sha256,createHash('sha256').update(canonicalForecastDisplayJson(readSignalDisplay(base))).digest('hex'));
  assert.deepEqual(result.scope,{captured_at:captured,game_date_before:'2026-10-14',source_observed_before:selected,source_cutoff_kind:'model_selection'});
  assert.deepEqual({base,logs},before);
});

test('all sports keep original selected-source bounds and legacy capture fallback private',()=>{
  for(const [sport,version,policy,id,prop] of [
    ['nba','empirical-jeffreys-v4-nba-source-asof-v1','nba-source-asof-v1','123','points'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','receptions'],
    ['cfb','empirical-jeffreys-v4-cfb-history-v1','cfb-explicit-receiving-v1','123','receptions']]) {
    const signal={...base,sport,model_version:version,history_policy_version:policy,player_id:id,prop_type:prop};
    const logs=[row('2026-10-12',2,{player_id:id,[prop]:2})];
    const result=forecastHistoryDisplay(signal,revision,source(logs));
    assert.equal(result.status,'available');assert.equal(result.scope.source_observed_before,selected);
    assert.equal(result.scope.source_cutoff_kind,'model_selection');
    const missing=forecastHistoryDisplay({...signal,history_observed_before:undefined},revision,source(logs));
    assert.equal(missing.status,'unavailable');assert.equal(missing.reason,'forecast_timing_unavailable');
    const legacy={...signal,model_version:'empirical-jeffreys-v4',history_policy_version:undefined,history_observed_before:selected};
    const legacyResult=forecastHistoryDisplay(legacy,revision,source(logs,{source_observed_before:captured}));
    assert.equal(legacyResult.status,'available');assert.equal(legacyResult.scope.source_cutoff_kind,'forecast_capture');
    assert.equal(legacyResult.scope.source_observed_before,captured);
  }
});

test('missing source and widened date/observation receipts cannot create verified history outputs',()=>{
  for(const read of [null,source([row('2026-10-12',3)],{game_date_before:'2026-10-15'}),
    source([row('2026-10-12',3)],{source_observed_before:captured})]) {
    const result=forecastHistoryDisplay(base,revision,read);
    assert.equal(result.status,'unavailable');assert.equal('windows' in result,false);
    assert.equal('card_summary' in result,false);assert.equal('source_coverage' in result,false);
  }
  for(const patch of [{captured_at:undefined},{captured_at:'2026-10-13T23:00:00Z'},
    {history_observed_before:'2026-10-14T01:01:01Z'},{forecast_cutoff:undefined}]) {
    assert.equal(forecastHistoryDisplay({...base,...patch},revision,source([])).status,'unavailable');
  }
});

test('duplicate, malformed or ambiguous athletes are unavailable while known missing stats stay null',()=>{
  const rows=[row('2026-10-12',3),row('2026-10-12',4)];
  assert.equal(forecastHistoryDisplay(base,revision,source(rows)).status,'unavailable');
  assert.equal(forecastHistoryDisplay({...base,player_id:undefined},revision,source([row('2026-10-12',3)])).status,'unavailable');
  assert.equal(forecastHistoryDisplay(base,revision,source([{...row('2026-10-12',3),player_id:'invalid'}])).status,'unavailable');
  const missing=forecastHistoryDisplay(base,revision,source([row('2026-10-12',undefined)]));
  assert.equal(missing.status,'available');assert.equal(missing.windows['20'].mean,null);
  assert.equal(missing.windows['20'].rate,null);assert.equal(missing.calendar.allTeams.observed,0);
});

test('PRA components, signed football yards and the 20-record retrieval disclosure preserve old behavior',()=>{
  const nba={...base,sport:'nba',player_id:'123',prop_type:'pra',line:10,direction:'over',
    model_version:'empirical-jeffreys-v4-nba-source-asof-v1',history_policy_version:'nba-source-asof-v1'};
  const logs=[row('2026-10-12',undefined,{player_id:'123',points:6,rebounds:4,assists:1}),
    row('2026-10-11',undefined,{player_id:'123',points:6,rebounds:4})];
  const result=forecastHistoryDisplay(nba,revision,source(logs));
  assert.equal(result.status,'available');assert.deepEqual(result.windows['20'].rows.map(row=>row.stat),[11,null]);
  const rush={...base,prop_type:'rush_yds',line:1};
  assert.equal(forecastHistoryDisplay(rush,revision,source([row('2026-10-12',undefined,{rush_yds:-2})])).windows['20'].rows[0].stat,-2);
  const full=Array.from({length:24},(_,index)=>row(new Date(Date.parse('2026-10-13')-index*86400000).toISOString().slice(0,10),index));
  const limited=forecastHistoryDisplay(base,revision,source(full));
  assert.equal(limited.status,'available');assert.equal(limited.windows['10'].rows.length,10);assert.equal(limited.windows['20'].rows.length,20);
  assert.equal(limited.calendar.limitedToLatest20,true);assert.match(limited.card_summary,/Only the latest 20 records/);
  assert.equal(limited.recent.recent.games,5);assert.equal(limited.recent.previous.games,5);
});

test('exact captured roster aliases determine team summaries, independent of later same-name/profile changes',()=>{
  for(const [sport,roster,stat,id,prop,version,policy] of [
    ['nfl','LAR','LA','00-0000001','receptions','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1'],
    ['nba','GS','GSW','123','points','empirical-jeffreys-v4-nba-source-asof-v1','nba-source-asof-v1']]) {
    const signal={...base,sport,player_id:id,prop_type:prop,model_version:version,history_policy_version:policy,
      availability:{...base.availability,team:roster}};
    const result=forecastHistoryDisplay(signal,revision,source([row('2026-10-12',3,{player_id:id,team:stat,[prop]:3}),
      row('2026-10-11',9,{player_id:id,team:'OTHER',[prop]:9}),row('2026-10-10',99,{player_id:id==='123'?'456':'00-0000002',team:stat,[prop]:99})]));
    assert.equal(result.status,'available');assert.equal(result.calendar.allTeams.games,2);
    assert.equal(result.calendar.capturedTeam,roster);assert.equal(result.calendar.capturedTeamSample.games,1);
    assert.equal(result.calendar.capturedTeamSample.mean,3);
  }
});

test('the emitted binding rejects changed record, source scope and revision without live/settlement fields',()=>{
  const result=forecastHistoryDisplay(base,revision,source([row('2026-10-12',3)]));
  const expected=binding(result);
  assert.deepEqual(readForecastHistoryDisplay(result,expected),result);
  for(const mutate of [value=>{value.subject.line=4.5;},value=>{value.subject.player_id='00-0000002';},
    value=>{value.subject.forecast_record_sha256='b'.repeat(64);},value=>{value.scope.source_observed_before= captured;},
    value=>{value.revision='b'.repeat(64);}]) {
    const changed=structuredClone(result);mutate(changed);assert.equal(readForecastHistoryDisplay(changed,expected),null);
  }
  for(const key of ['actionable_until','gated','qualified','settlement','raw_evidence','source_payload']) assert.equal(key in result,false);
});

test('validated participation labels retain existing dated and separate recent-window wording',()=>{
  const split={player:'Teammate',status:'Questionable',position:'WR',team:'BUF',relationship:'teammate',unit:'offense',
    source:'nflverse_snap_counts',participation:'recorded unit snaps',evidence_version:'recorded-participation-v3',unknown_games:1,
    active:{games:1,mean:5,hit_rate:1},absent:{games:0,mean:null,hit_rate:null},
    sample_window:{cutoff:base.forecast_cutoff,active:{oldest:'2026-10-12',newest:'2026-10-12'},absent:null,
      unknown:{oldest:'2026-10-11',newest:'2026-10-11'}}};
  const signal={...base,availability:{...base.availability,context_splits:[split]}};
  const result=forecastHistoryDisplay(signal,revision,source([]));
  assert.equal(result.status,'available');assert.deepEqual(result.context_labels,[{player:'Teammate',team:'BUF',
    relationship:'teammate',unit:'offense',window:contextWindowText(split),recent:recentParticipationText(split)}]);
  assert.match(result.context_labels[0].recent,/not retained/);
  assert.equal('source' in result.context_labels[0],false);assert.equal('raw_evidence' in result.context_labels[0],false);
});
