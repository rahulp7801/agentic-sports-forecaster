import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {buildImmutableHistoryDisplay,IMMUTABLE_HISTORY_DISPLAY_PRODUCER_VERSION} from '../lib/immutableForecastHistoryDisplay.ts';
import {IMMUTABLE_FORECAST_QUERY} from '../lib/immutableForecastHistory.ts';
import {canonicalForecastDisplayJson} from '../lib/forecastDisplayPacket.ts';
import {readSignalDisplay} from '../lib/signalDisplay.ts';
import {readForecastHistoryDisplay} from '../lib/forecastHistoryDisplay.ts';
import {forecastHistory,recentForm,calendarForm} from '../lib/forecastHistory.ts';
import {pickCardFormSummary} from '../lib/pickCardForm.ts';

const id='a'.repeat(64),revision='b'.repeat(64),now=Date.parse('2026-10-14T02:00:00Z');
const stamp='2026-10-14T01:00:00Z',selected='2026-10-14T01:00:10Z',captured='2026-10-14T01:01:00Z';
const secret='PRIVATE_RESEARCH_MUST_NOT_LEAVE_THE_BRIDGE';
const base={id,player:'Synthetic Athlete',player_id:'00-0000001',team:'BUF',opponent:'DET',
  home_team:'Home',away_team:'Away',game_id:'fixture-game',sport:'nfl',prop_type:'receptions',line:4,direction:'under',
  true_prob:.6,implied_prob:.5,ev_pct:.1,expected_return:.2,push_probability:0,confidence_interval:[.55,.7],
  model_version:'empirical-jeffreys-v4-nfl-history-v1',history_policy_version:'nfl-explicit-receiving-v1',
  history_observed_before:selected,forecast_cutoff:'2026-10-14',snapped_at:stamp,captured_at:captured,
  game_start_time:'2026-10-15T00:00:00Z',kelly_fraction:.01,american_odds:100,sportsbook:'draftkings',
  trade_plan:[],injury_flags:{},market_type:'player_receptions',strength:'unrated',gated:false,sample_size:40,mean_stat:5,
  availability:{status:'observed',roster_confirmed:true,subject_status:'Active',probability_adjusted:false,
    captured_at:stamp,team:'BUF',teammates:[],source_url:'https://example.test/injuries',source_sha256:'c'.repeat(64),
    roster_source_url:'https://example.test/roster',roster_source_sha256:'d'.repeat(64)}};

function publicHash(record) {
  const projected=readSignalDisplay(record);assert.ok(projected,'Fixture must be a valid public shape');
  return createHash('sha256').update(canonicalForecastDisplayJson(projected)).digest('hex');
}
function fixture({shared={},rawPatch={},recordPatch={},recordedAt='2026-10-14T01:01:00.000100Z'}={}) {
  const common={...structuredClone(base),...shared};
  const record={...structuredClone(common),...recordPatch};
  const raw={game_id:common.game_id,sport:common.sport,player:common.player,player_id:common.player_id,
    prop_type:common.prop_type,line:common.line,direction:common.direction,quote_time:common.snapped_at,
    model_generated_at:'2026-10-14T01:00:30Z',captured_at:common.captured_at,game_start_time:common.game_start_time,
    model_version:common.model_version,history_policy_version:common.history_policy_version,
    history_observed_before:common.history_observed_before,forecast_cutoff:common.forecast_cutoff,
    availability:common.availability,model_probability:.61,accepted:false,stake_fraction:0,private_research:secret,...rawPatch};
  const payload=JSON.stringify(raw,null,2),payload_sha256=createHash('sha256').update(payload,'utf8').digest('hex');
  return {record,raw,row:{id,scan_id:'synthetic-scan',payload,payload_sha256,recorded_at:recordedAt},
    request:{id,payload_sha256,forecast_record_sha256:publicHash(record),revision}};
}
function log(date,value,patch={}) {
  return {date,player:base.player,player_id:base.player_id,team:'BUF',opponent:'DET',
    ...(value===undefined ? {} : {receptions:value}),...patch};
}
const wrap=logs=>logs.map(payload=>({payload}));
function core(payload,sourcePatch={}) {
  const source={player_id:payload.player_id,season:2026,week:5,team:payload.team,
    passing_yards:payload.pass_yds,rushing_yards:payload.rush_yds,receiving_yards:null,receptions:null,...sourcePatch};
  const ordered=Object.fromEntries(Object.keys(source).sort().map(key=>[key,source[key]]));
  const source_row={...source,source_record_sha256:createHash('sha256').update(JSON.stringify(ordered)).digest('hex')};
  return {payload,source_row};
}
async function run(data,rows=[],overrides={},clock=now) {
  const calls={prediction:[],approved:[],history:[]};
  const reads={predictionRead:async(sql,args)=>{calls.prediction.push({sql,args:[...args]});return [data.row];},
    approvedRecordRead:async request=>{calls.approved.push({...request});return {revision,record:data.record};},
    historyRead:async(sql,args)=>{calls.history.push({sql,args:[...args]});return rows;},...overrides};
  return {result:await buildImmutableHistoryDisplay(data.request,reads,clock),calls};
}
function display(result) {
  assert.equal(result.status,'resolved');assert.equal(result.display.status,'available');return result.display;
}
function unavailableHistory(result,data,reason='history_records_unavailable') {
  assert.equal(result.status,'resolved');assert.equal(result.display.status,'unavailable');assert.equal(result.display.reason,reason);
  assert.deepEqual(result.display.subject,{forecast_id:id,forecast_record_sha256:data.request.forecast_record_sha256,
    sport:data.record.sport,player:data.record.player,player_id:data.record.player_id,prop_type:data.record.prop_type,
    line:data.record.line,direction:data.record.direction});
  assert.equal(result.display.scope.game_date_before,data.raw.forecast_cutoff);
  assert.equal(result.display.scope.source_observed_before,data.raw.history_observed_before ?? data.raw.captured_at);
  for(const key of ['windows','recent','calendar','card_summary','source_coverage','context_labels']) assert.equal(Object.hasOwn(result.display,key),false);
}

test('independent raw receipt and approved record commitments preserve original descriptive numeric outputs',async()=>{
  const data=fixture(),logs=[log('2026-10-13'),log('2026-10-12',0),log('2026-10-11',4),log('2026-10-10',8),
    log('2026-10-09',3),log('2026-10-08',2),log('2026-09-01',40)];
  const before=structuredClone({data,logs}),{result,calls}=await run(data,wrap(logs)),value=display(result);
  assert.notEqual(data.request.payload_sha256,data.request.forecast_record_sha256);
  assert.deepEqual(calls.prediction,[{sql:IMMUTABLE_FORECAST_QUERY,args:[id,data.row.payload_sha256]}]);
  assert.deepEqual(calls.approved,[{id,revision}]);assert.equal(calls.history.length,1);
  assert.match(calls.history[0].sql,/dashboard_gamelog_versions/);
  assert.deepEqual(calls.history[0].args,['nfl','',20,'2026-10-14',true,base.player_id,selected]);
  assert.deepEqual(value.windows['10'],forecastHistory(logs,data.record,10));
  assert.deepEqual(value.windows['20'],forecastHistory(logs,data.record,20));
  assert.deepEqual(value.recent,recentForm(logs,data.record));assert.deepEqual(value.calendar,calendarForm(logs,data.record));
  assert.equal(value.card_summary,pickCardFormSummary(logs,data.record));
  assert.equal(value.producer_version,IMMUTABLE_HISTORY_DISPLAY_PRODUCER_VERSION);
  assert.deepEqual(value.scope,{captured_at:captured,game_date_before:'2026-10-14',source_observed_before:selected,source_cutoff_kind:'model_selection'});
  assert.deepEqual(value.context_labels,[]);assert.equal(value.source_coverage,'bounded_as_of_records');
  assert.deepEqual(readForecastHistoryDisplay(value,{revision,subject:value.subject,scope:value.scope}),value);
  assert.deepEqual({data,logs},before);
});

test('no original raw TEXT, source proof, receipt metadata or forecast decisions appear in resolved output',async()=>{
  const data=fixture({recordPatch:{private_research:secret}}),rows=wrap([log('2026-10-12',3,{private_research:secret})]);
  const value=display((await run(data,rows)).result),encoded=JSON.stringify(value);
  assert.equal(encoded.includes(secret),false);assert.equal(encoded.includes(data.row.payload_sha256),false);
  assert.equal(encoded.includes(data.row.scan_id),false);assert.equal(encoded.includes(data.row.recorded_at),false);
  const forbidden=new Set(['payload','source_row','receipt','record','accepted','stake_fraction','model_probability',
    'true_prob','ev_pct','qualified','gated','raw_evidence','source_payload']);
  function check(item) {
    if(!item||typeof item!=='object') return;
    for(const [key,child] of Object.entries(item)) {assert.equal(forbidden.has(key),false,key);check(child);}
  }
  check(value);assert.equal(value.subject.forecast_record_sha256,data.request.forecast_record_sha256);
});

test('exact four-field admission prevents caller-selected identity, market, cutoff and source scope',async()=>{
  const data=fixture();let calls=0;
  const reads={predictionRead:async()=>{calls++;return [data.row];},approvedRecordRead:async()=>{calls++;return {revision,record:data.record};},historyRead:async()=>{calls++;return [];}};
  for(const extra of [{sport:'nba'},{player_id:'00-0000002'},{line:1},{observed_before:captured},
    {forecast_cutoff:'2026-10-15'},{prop_type:'rush_yds'}]) {
    assert.deepEqual(await buildImmutableHistoryDisplay({...data.request,...extra},reads,now),{status:'unavailable',reason:'invalid_request'});
  }
  for(const request of [null,[],{id}, {...data.request,id:'A'.repeat(64)}, {...data.request,revision:'bad'},
    {...data.request,payload_sha256:1},{...data.request,forecast_record_sha256:'bad'}]) {
    assert.deepEqual(await buildImmutableHistoryDisplay(request,reads,now),{status:'unavailable',reason:'invalid_request'});
  }
  for(const callbacks of [null,[],{...reads,unused:()=>{}},{...reads,historyRead:null}]) {
    assert.deepEqual(await buildImmutableHistoryDisplay(data.request,callbacks,now),{status:'unavailable',reason:'invalid_request'});
  }
  assert.equal(calls,0);
});

test('accessor, hidden, symbolic and hostile request/callback descriptors reject without invoking user code',async()=>{
  const data=fixture();let calls=0,getters=0;
  const reads={predictionRead:async()=>{calls++;return [];},approvedRecordRead:async()=>{calls++;return null;},historyRead:async()=>{calls++;return [];}};
  const accessor={...data.request};Object.defineProperty(accessor,'id',{enumerable:true,get(){getters++;throw Error(secret);}});
  const hidden={...data.request};Object.defineProperty(hidden,'private',{value:secret});
  const symbolic={...data.request,[Symbol('private')]:secret};
  for(const request of [accessor,hidden,symbolic,new Proxy(data.request,{getPrototypeOf(){throw Error(secret);}})]) {
    assert.deepEqual(await buildImmutableHistoryDisplay(request,reads,now),{status:'unavailable',reason:'invalid_request'});
  }
  const callbackAccessor={...reads};Object.defineProperty(callbackAccessor,'historyRead',{enumerable:true,get(){getters++;throw Error(secret);}});
  assert.deepEqual(await buildImmutableHistoryDisplay(data.request,callbackAccessor,now),{status:'unavailable',reason:'invalid_request'});
  assert.equal(calls,0);assert.equal(getters,0);
});

test('request and reader functions are snapshotted before awaits and property get traps are never invoked',async()=>{
  const data=fixture(),request={...data.request};let traps=0,wrongCalls=0;
  const proxy=new Proxy(request,{get(){traps++;throw Error(secret);}});
  const reads={predictionRead:async(sql,args)=>{
    assert.equal(sql,IMMUTABLE_FORECAST_QUERY);assert.deepEqual(args,[id,data.row.payload_sha256]);
    request.id='c'.repeat(64);request.revision='d'.repeat(64);request.forecast_record_sha256='e'.repeat(64);
    reads.approvedRecordRead=async()=>{wrongCalls++;return null;};reads.historyRead=async()=>{wrongCalls++;return null;};
    return [data.row];},approvedRecordRead:async wanted=>{
    assert.deepEqual(wanted,{id,revision});wanted.id='f'.repeat(64);wanted.revision='f'.repeat(64);
    return {revision,record:data.record};},historyRead:async(sql,args)=>{
    assert.match(sql,/dashboard_gamelog_versions/);assert.deepEqual(args,['nfl','',20,'2026-10-14',true,base.player_id,selected]);return [];
  }};
  const value=display(await buildImmutableHistoryDisplay(proxy,reads,now));
  assert.equal(value.subject.forecast_id,id);assert.equal(value.revision,revision);assert.equal(traps,0);assert.equal(wrongCalls,0);
});

test('missing, corrupt, ambiguous and failed retained receipt reads short circuit approved and history lookups',async()=>{
  const data=fixture();
  for(const [prediction,reason] of [[[], 'prediction_unavailable'],[[data.row,data.row],'prediction_unavailable'],
    [[{...data.row,payload_sha256:'c'.repeat(64)}],'receipt_unavailable'],[[{...data.row,recorded_at:null}],'receipt_unavailable'],
    [[{...data.row,payload:JSON.stringify(data.raw)}],'receipt_unavailable'],[[{...data.row,id:'c'.repeat(64)}],'receipt_unavailable']]) {
    const {result,calls}=await run(data,[],{predictionRead:async()=>prediction});
    assert.deepEqual(result,{status:'unavailable',reason});assert.equal(calls.approved.length,0);assert.equal(calls.history.length,0);
  }
  const {result,calls}=await run(data,[],{predictionRead:async()=>{throw Error(secret);}});
  assert.deepEqual(result,{status:'unavailable',reason:'prediction_unavailable'});assert.equal(calls.approved.length,0);assert.equal(calls.history.length,0);
  const swapped={...data,request:{...data.request,payload_sha256:data.request.forecast_record_sha256}};
  assert.deepEqual((await run(swapped)).result,{status:'unavailable',reason:'receipt_unavailable'});
});

test('late or microscopically reordered source, model, capture and receipt instants never reach later readers',async()=>{
  for(const data of [fixture({recordedAt:base.game_start_time.replace('Z','.000000Z')}),
    fixture({rawPatch:{model_generated_at:'2026-10-14T01:01:00.000001Z'}}),
    fixture({rawPatch:{history_observed_before:'2026-10-14T01:00:30.000001Z'}}),
    fixture({rawPatch:{availability:{...base.availability,captured_at:'2026-10-14T01:01:00.000001Z'}}})]) {
    const {result,calls}=await run(data);
    assert.deepEqual(result,{status:'unavailable',reason:'chronology_unavailable'});assert.equal(calls.approved.length,0);assert.equal(calls.history.length,0);
  }
});

test('approved reader errors, wrong envelope shapes and invalid records have fixed unavailable responses',async()=>{
  const data=fixture();
  for(const envelope of [null,[],{revision}, {revision,record:data.record,receipt:data.row},
    {revision,record:{...data.record,gated:undefined}}, {revision,record:{...data.record,american_odds:99}}]) {
    const {result,calls}=await run(data,[],{approvedRecordRead:async()=>envelope});
    assert.deepEqual(result,{status:'unavailable',reason:'approved_record_unavailable'});assert.equal(calls.history.length,0);
  }
  const {result,calls}=await run(data,[],{approvedRecordRead:async()=>{throw Error(secret);}});
  assert.deepEqual(result,{status:'unavailable',reason:'approved_record_unavailable'});assert.equal(calls.history.length,0);
});

test('public revision and projected record hash must independently match before any history read',async()=>{
  const data=fixture();
  for(const envelope of [{revision:'c'.repeat(64),record:data.record},{revision,record:{...data.record,true_prob:.7}},
    {revision,record:{...data.record,american_odds:110}}]) {
    const {result,calls}=await run(data,[],{approvedRecordRead:async()=>envelope});
    assert.deepEqual(result,{status:'unavailable',reason:'approved_record_mismatch'});assert.equal(calls.history.length,0);
  }
  const swapped={...data,request:{...data.request,forecast_record_sha256:data.request.payload_sha256}};
  assert.deepEqual((await run(swapped)).result,{status:'unavailable',reason:'approved_record_mismatch'});
});

test('a freshly correct public hash cannot bind changed immutable identity, terms or retained source fields',async()=>{
  for(const patch of [{id:'c'.repeat(64)},{game_id:'other-game'},{sport:'cfb'},{player:'Other Athlete'},
    {player_id:'00-0000002'},{prop_type:'rec_yds'},{line:4.5},{direction:'over'},
    {snapped_at:'2026-10-14T00:59:59Z'},{captured_at:'2026-10-14T01:01:00.000001Z'},
    {game_start_time:'2026-10-15T00:01:00Z'},{model_version:'empirical-jeffreys-v4'},
    {forecast_cutoff:'2026-10-15'},{history_policy_version:'other-policy'},
    {history_observed_before:'2026-10-14T01:00:10.000001Z'}]) {
    const data=fixture({recordPatch:patch}),{result,calls}=await run(data);
    assert.deepEqual(result,{status:'unavailable',reason:'approved_record_mismatch'},JSON.stringify(patch));assert.equal(calls.history.length,0);
  }
});

test('observed retained availability requires the original status, roster, team and observation timestamp',async()=>{
  for(const patch of [{status:'unavailable',roster_confirmed:false},{team:'KC'},
    {captured_at:'2026-10-14T01:00:00.000001Z'}]) {
    const data=fixture({recordPatch:{availability:{...base.availability,...patch}}}),{result,calls}=await run(data);
    assert.deepEqual(result,{status:'unavailable',reason:'approved_record_mismatch'});assert.equal(calls.history.length,0);
  }
  const data=fixture({recordPatch:{availability:{...base.availability,subject_status:'Questionable'}}});
  assert.equal(display((await run(data)).result).calendar.capturedTeam,'BUF');
});

test('unavailable and absent retained availability cannot create verified current-team or participation context',async()=>{
  const unavailable={status:'unavailable',roster_confirmed:false,subject_status:'Unknown',probability_adjusted:false,teammates:[]};
  const data=fixture({shared:{availability:unavailable},recordPatch:{availability:{...unavailable,team:'KC',captured_at:captured}}});
  const value=display((await run(data,wrap([log('2026-10-12',3)]))).result);
  assert.equal(value.calendar.capturedTeam,null);assert.equal(value.calendar.capturedTeamSample,null);assert.deepEqual(value.context_labels,[]);
  assert.equal(value.card_summary,'Current-team form was not verified at forecast capture.');
  const absent=fixture({rawPatch:{availability:undefined}});delete absent.record.availability;
  absent.request.forecast_record_sha256=publicHash(absent.record);
  assert.equal(display((await run(absent)).result).calendar.capturedTeam,null);
  const mismatch=fixture({rawPatch:{availability:undefined}});
  assert.deepEqual((await run(mismatch)).result,{status:'unavailable',reason:'approved_record_mismatch'});
});

test('approved numeric metrics have their own trusted commitment and are not fabricated or certified from minimal raw context',async()=>{
  const data=fixture({recordPatch:{true_prob:.75,expected_return:.5,american_odds:120,ev_pct:.25}});
  assert.equal(data.raw.model_probability,.61);const value=display((await run(data,wrap([log('2026-10-12',3)]))).result);
  assert.equal(value.windows['20'].mean,3);assert.equal(value.windows['20'].rate,1);
  for(const key of ['true_prob','expected_return','american_odds','ev_pct','model_probability']) assert.equal(Object.hasOwn(value,key),false);
});

test('later approved participation enrichment cannot manufacture retained labels from the minimal immutable context',async()=>{
  const split={player:'Teammate',status:'Questionable',position:'WR',team:'BUF',relationship:'teammate',unit:'offense',
    source:'nflverse_snap_counts',participation:'recorded unit snaps',evidence_version:'recorded-participation-v3',unknown_games:1,
    active:{games:1,mean:5,hit_rate:1},absent:{games:0,mean:null,hit_rate:null},
    sample_window:{cutoff:'2026-10-14',active:{oldest:'2026-10-12',newest:'2026-10-12'},absent:null,
      unknown:{oldest:'2026-10-11',newest:'2026-10-11'}}};
  const data=fixture({recordPatch:{availability:{...base.availability,context_splits:[split]}}});
  assert.equal(data.raw.availability.context_splits,undefined);
  assert.deepEqual(display((await run(data,[])).result).context_labels,[]);
});

test('approved callback records reject getters, hidden fields, exotic objects and oversized data without executing them',async()=>{
  const data=fixture();let getters=0;
  const accessor=structuredClone(data.record);Object.defineProperty(accessor,'line',{enumerable:true,get(){getters++;throw Error(secret);}});
  const hidden=structuredClone(data.record);Object.defineProperty(hidden,'private',{value:secret});
  const nested=structuredClone(data.record);Object.defineProperty(nested.availability,'private',{enumerable:true,get(){getters++;throw Error(secret);}});
  const bad=[accessor,hidden,nested,{...data.record,private:new Date()}, {...data.record,private:BigInt(1)},
    {...data.record,private:'🙂'.repeat(270000)},new Proxy(data.record,{ownKeys(){throw Error(secret);}})];
  for(const record of bad) {
    const {result,calls}=await run(data,[],{approvedRecordRead:async()=>({revision,record})});
    assert.deepEqual(result,{status:'unavailable',reason:'approved_record_unavailable'});assert.equal(calls.history.length,0);
  }
  assert.equal(getters,0);
});

test('healthy empty history remains available while known missing statistics stay null',async()=>{
  const data=fixture(),empty=display((await run(data,[])).result);
  assert.deepEqual(empty.windows['20'],forecastHistory([],data.record,20));assert.equal(empty.windows['20'].rate,null);
  assert.equal(empty.calendar.allTeams.games,0);assert.equal(empty.recent.meanChange,null);
  const missing=display((await run(data,wrap([log('2026-10-12')]))).result);
  assert.equal(missing.windows['20'].rows[0].stat,null);assert.equal(missing.windows['20'].missing,1);
  assert.equal(missing.windows['20'].mean,null);assert.equal(missing.windows['20'].rate,null);assert.equal(missing.calendar.allTeams.observed,0);
});

test('failed and malformed history sources retain bound subject/scope without manufacturing empty success',async()=>{
  const data=fixture();
  for(const rows of [null,undefined,{},[null],[{payload:[]}],[{payload:log('2026-10-12',3),extra:secret}],
    [{payload:log('2026-10-12',3),source_row:{}}],Array(1),Array.from({length:21},()=>({payload:log('2026-10-12',3)}))]) {
    unavailableHistory((await run(data,[],{historyRead:async()=>rows})).result,data);
  }
  const {result}=await run(data,[],{historyRead:async()=>{throw Error(secret);}});
  unavailableHistory(result,data,'history_source_unavailable');assert.equal(JSON.stringify(result).includes(secret),false);
});

test('wrong or missing athletes, target/future dates, malformed dates and duplicates invalidate the entire history source',async()=>{
  const data=fixture();
  const missing=log('2026-10-12',3);delete missing.player_id;
  for(const logs of [[log('2026-10-12',3,{player_id:'00-0000002'})],[missing],
    [log('2026-10-14',3)],[log('2026-10-15',3)],[log('2026-02-30',3)],
    [log('2026-10-12',3),log('2026-10-12',4)],[log('2026-10-12',3),log('2026-10-11',3,{player_id:'00-0000002'})]]) {
    unavailableHistory((await run(data,wrap(logs))).result,data);
  }
});

test('history callback getters, symbols, proxies, extra array entries and oversized payloads fail closed',async()=>{
  const data=fixture();let getters=0;
  const accessor={};Object.defineProperty(accessor,'payload',{enumerable:true,get(){getters++;throw Error(secret);}});
  const payload=log('2026-10-12',3);Object.defineProperty(payload,'private',{enumerable:true,get(){getters++;throw Error(secret);}});
  const hidden={payload:log('2026-10-12',3)};Object.defineProperty(hidden,'private',{value:secret});
  const extra=wrap([log('2026-10-12',3)]);extra.extra=secret;
  for(const rows of [[accessor],[{payload}],[hidden],[{payload:log('2026-10-12',3),[Symbol('private')]:secret}],extra,
    [{payload:log('2026-10-12',3,{private:'🙂'.repeat(270000)})}],new Proxy([],{getPrototypeOf(){throw Error(secret);}})]) {
    unavailableHistory((await run(data,rows)).result,data);
  }
  assert.equal(getters,0);
});

test('all sports and NFL core props use retained stable identities and fixed bounded as-of query arguments',async()=>{
  for(const [sport,version,policy,player_id,prop_type,view] of [
    ['nba','empirical-jeffreys-v4-nba-source-asof-v1','nba-source-asof-v1','123','points','dashboard_gamelogs_asof'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','receptions','dashboard_gamelog_versions'],
    ['cfb','empirical-jeffreys-v4-cfb-history-v1','cfb-explicit-receiving-v1','123','rec_yds','dashboard_gamelog_versions'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','pass_yds','dashboard_nfl_core_gamelogs_asof'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','rush_yds','dashboard_nfl_core_gamelogs_asof']]) {
    const data=fixture({shared:{sport,model_version:version,history_policy_version:policy,player_id,prop_type,line:2,direction:'over'}});
    const payload=log('2026-10-12',undefined,{player_id,[prop_type]:3});
    const rows=prop_type==='pass_yds'||prop_type==='rush_yds' ? [core({...payload,pass_yds:250,rush_yds:-2})] : wrap([payload]);
    const {result,calls}=await run(data,rows),value=display(result);
    assert.match(calls.history[0].sql,new RegExp(view));
    assert.deepEqual(calls.history[0].args,[sport,'',20,'2026-10-14',true,player_id,selected]);
    assert.equal(value.scope.source_cutoff_kind,'model_selection');assert.equal(value.subject.prop_type,prop_type);
    assert.equal(value.windows['20'].rows[0].stat,prop_type==='pass_yds' ? 250 : prop_type==='rush_yds' ? -2 : 3);
  }
});

test('legacy model history uses original capture fallback without changing source policy versions',async()=>{
  const data=fixture({shared:{model_version:'empirical-jeffreys-v4',history_policy_version:undefined}});
  delete data.record.history_policy_version;data.request.forecast_record_sha256=publicHash(data.record);
  const {result,calls}=await run(data,wrap([log('2026-10-12',3)])),value=display(result);
  assert.equal(value.scope.source_cutoff_kind,'forecast_capture');assert.equal(value.scope.source_observed_before,captured);
  assert.equal(calls.history[0].args[6],captured);
  assert.deepEqual(value.windows['20'],forecastHistory([log('2026-10-12',3)],data.record,20));
});

test('NFL passing/rushing require matching committed source rows before exposing signed or missing yards',async()=>{
  for(const prop_type of ['pass_yds','rush_yds']) {
    const data=fixture({shared:{prop_type,line:1,direction:'over'}});
    const original=core(log('2026-10-12',undefined,{pass_yds:250,rush_yds:-2}));
    const value=display((await run(data,[original])).result);
    assert.equal(value.windows['20'].rows[0].stat,prop_type==='pass_yds' ? 250 : -2);
    const missing=core(log('2026-10-12',undefined,{pass_yds:null,rush_yds:null}));
    assert.equal(display((await run(data,[missing])).result).windows['20'].rows[0].stat,null);
    for(const row of [{payload:original.payload}, {...original,source_row:{...original.source_row,source_record_sha256:'c'.repeat(64)}},
      {...original,payload:{...original.payload,pass_yds:251}}, {...original,payload:{...original.payload,team:'KC'}},
      core({...original.payload,player_id:'00-0000002'}), {...original,source_row:{...original.source_row,extra:secret}}]) {
      unavailableHistory((await run(data,[row])).result,data);
    }
  }
});

test('NBA PRA components, exact roster aliases and latest-20 disclosure keep original descriptive behavior',async()=>{
  const data=fixture({shared:{sport:'nba',player_id:'123',prop_type:'pra',line:10,direction:'over',
    model_version:'empirical-jeffreys-v4-nba-source-asof-v1',history_policy_version:'nba-source-asof-v1',
    availability:{...base.availability,team:'GS'}}});
  const logs=Array.from({length:20},(_,index)=>log(new Date(Date.parse('2026-10-13')-index*86400000).toISOString().slice(0,10),undefined,
    {player_id:'123',team:index===1 ? 'OTHER' : 'GSW',points:6,rebounds:4,...(index===2 ? {} : {assists:1})}));
  const value=display((await run(data,wrap(logs))).result);
  assert.deepEqual(value.windows['20'],forecastHistory(logs,data.record,20));
  assert.deepEqual(value.calendar,calendarForm(logs,data.record));assert.equal(value.calendar.capturedTeam,'GS');
  assert.equal(value.calendar.capturedTeamSample.games,19);assert.equal(value.windows['20'].rows[2].stat,null);
  assert.equal(value.windows['10'].rows.length,10);assert.equal(value.windows['20'].rows.length,20);
  assert.equal(value.calendar.limitedToLatest20,true);assert.match(value.card_summary,/Only the latest 20 records/);
});

test('same-millisecond original capture and DB receipt before kickoff resolve without millisecond chronology collapse',async()=>{
  const shared={snapped_at:'2026-10-14T01:00:00.000100+00:00',history_observed_before:'2026-10-14T01:00:00.000300+00:00',
    captured_at:'2026-10-14T01:00:00.000500+00:00',game_start_time:'2026-10-14T01:00:00.000900+00:00',
    availability:{...base.availability,captured_at:'2026-10-14T01:00:00.000250+00:00'}};
  const data=fixture({shared,rawPatch:{model_generated_at:'2026-10-14T01:00:00.000400+00:00'},recordedAt:'2026-10-14T01:00:00.000600Z'});
  assert.equal(Date.parse(shared.captured_at),Date.parse(shared.game_start_time));
  const {result,calls}=await run(data,wrap([log('2026-10-12',3)])),value=display(result);
  assert.equal(value.scope.captured_at,shared.captured_at);assert.equal(value.scope.source_observed_before,shared.history_observed_before);
  assert.equal(calls.history[0].args[6],shared.history_observed_before);assert.equal(value.calendar.capturedTeam,'BUF');
  assert.equal(value.windows['20'].rate,1);assert.deepEqual(value.context_labels,[]);
  const late=fixture({shared,rawPatch:{model_generated_at:'2026-10-14T01:00:00.000400+00:00'},recordedAt:'2026-10-14T01:00:00.000900Z'});
  const rejected=await run(late);assert.deepEqual(rejected.result,{status:'unavailable',reason:'chronology_unavailable'});
  assert.equal(rejected.calls.approved.length,0);assert.equal(rejected.calls.history.length,0);
});
