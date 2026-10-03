import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {IMMUTABLE_FORECAST_QUERY,resolveImmutableForecast} from '../lib/immutableForecastHistory.ts';

const id='a'.repeat(64),now=Date.parse('2026-10-14T18:00:00Z');
const raw={game_id:'fixture-game',sport:'nfl',player:'Synthetic Athlete',player_id:'00-0000001',
  prop_type:'pass_yds',line:249.5,direction:'over',model_version:'empirical-jeffreys-v4-nfl-history-v1',
  history_policy_version:'nfl-explicit-receiving-v1',forecast_cutoff:'2026-10-14',
  quote_time:'2026-10-14T17:00:00.000100+00:00',history_observed_before:'2026-10-14T17:00:00.000300+00:00',
  model_generated_at:'2026-10-14T17:00:00.000400+00:00',captured_at:'2026-10-14T17:00:00.000500+00:00',
  game_start_time:'2026-10-14T21:00:00+00:00',accepted:false,stake_fraction:0,model_probability:.61,
  private_research:'PRIVATE_PAYLOAD_MUST_STAY_PRIVATE',
  availability:{status:'observed',roster_confirmed:true,captured_at:'2026-10-14T17:00:00.000250+00:00',
    team:'KC',private_research:'PRIVATE_PAYLOAD_MUST_STAY_PRIVATE'}};

function fixture(patch={},recorded_at='2026-10-14T17:00:00.000600Z') {
  const payload=JSON.stringify({...raw,...patch},null,2);
  const payload_sha256=createHash('sha256').update(payload,'utf8').digest('hex');
  return {row:{id,scan_id:'synthetic-scan',payload,payload_sha256,recorded_at},request:{id,payload_sha256}};
}

async function resolve(data,clock=now) {
  const calls=[];
  const result=await resolveImmutableForecast(data.request,async(sql,args)=>{
    calls.push({sql,args:[...args]});return [data.row];
  },clock);
  return {result,calls};
}

test('immutable lookup uses one fixed parameterized receipt read and prepares only the retained exact history query',async()=>{
  const data=fixture(),{result,calls}=await resolve(data);
  assert.equal(result.status,'resolved');assert.equal(calls.length,1);
  assert.equal(calls[0].sql,IMMUTABLE_FORECAST_QUERY);
  assert.deepEqual(calls[0].args,[data.request.id,data.request.payload_sha256]);
  assert.deepEqual(result.receipt,{id,scan_id:data.row.scan_id,payload_sha256:data.row.payload_sha256,
    recorded_at:data.row.recorded_at});
  assert.equal(result.context.snapped_at,raw.quote_time);
  assert.equal(result.context.history_observed_before,raw.history_observed_before);
  assert.equal(result.context.forecast_cutoff,raw.forecast_cutoff);
  assert.deepEqual(result.query.args,['nfl','',20,raw.forecast_cutoff,true,raw.player_id,raw.history_observed_before]);
  assert.match(result.query.sql,/dashboard_nfl_core_gamelogs_asof/);
  assert.match(result.query.sql,/game_date<\$4::date/);
  assert.match(result.query.sql,/record_available_at<=\$7::timestamptz/);
  assert.equal(JSON.stringify(result).includes(raw.private_research),false);
  for(const name of ['payload','accepted','stake_fraction','model_probability']) {
    assert.equal(Object.hasOwn(result.receipt,name),false);assert.equal(Object.hasOwn(result.context,name),false);
  }
});

test('request scope cannot override stored athlete, sport, market, line, cutoff or source timestamp',async()=>{
  const {request}=fixture();let calls=0;
  const read=async()=>{calls++;throw Error('Unexpected lookup');};
  for(const extra of [{sport:'nba'},{player_id:'00-0000002'},{prop_type:'rush_yds'},{line:1.5},
    {forecast_cutoff:'2026-10-15'},{observed_before:'2026-10-15T17:00:00Z'}]) {
    assert.deepEqual(await resolveImmutableForecast({...request,...extra},read,now),{status:'unavailable',reason:'invalid_request'});
  }
  for(const invalid of [null,[],{id}, {...request,id:'A'.repeat(64)}, {...request,payload_sha256:'invalid'}])
    assert.deepEqual(await resolveImmutableForecast(invalid,read,now),{status:'unavailable',reason:'invalid_request'});
  assert.equal(calls,0);
});

test('accessor and throwing Proxy requests fail admission without invoking a lookup or exposing errors',async()=>{
  const {request}=fixture();let reads=0,getters=0;
  const accessor=Object.defineProperties({}, {id:{enumerable:true,get(){getters++;throw Error('PRIVATE_REQUEST_DETAILS');}},
    payload_sha256:{enumerable:true,value:request.payload_sha256}});
  const hostile=[accessor,new Proxy(request,{getPrototypeOf(){throw Error('PRIVATE_REQUEST_DETAILS');}})];
  for(const value of hostile) {
    const result=await resolveImmutableForecast(value,async()=>{reads++;return [];},now);
    assert.deepEqual(result,{status:'unavailable',reason:'invalid_request'});
    assert.equal(JSON.stringify(result).includes('PRIVATE_REQUEST_DETAILS'),false);
  }
  assert.equal(reads,0);assert.equal(getters,0);
});

test('validated request data descriptors are frozen before callbacks without invoking Proxy property traps',async()=>{
  const data=fixture();let traps=0;
  const proxy=new Proxy(data.request,{get(){traps++;throw Error('PRIVATE_REQUEST_DETAILS');}});
  const calls=[];
  const result=await resolveImmutableForecast(proxy,async(sql,args)=>{
    calls.push({sql,args:[...args]});return [data.row];
  },now);
  assert.equal(result.status,'resolved');assert.equal(traps,0);
  assert.deepEqual(calls,[{sql:IMMUTABLE_FORECAST_QUERY,args:[id,data.row.payload_sha256]}]);
  assert.equal(JSON.stringify(result).includes(raw.private_research),false);
  const mutable={...data.request};
  const retained=await resolveImmutableForecast(mutable,async(sql,args)=>{
    assert.equal(sql,IMMUTABLE_FORECAST_QUERY);assert.deepEqual(args,[id,data.row.payload_sha256]);
    mutable.id='b'.repeat(64);mutable.payload_sha256='c'.repeat(64);return [data.row];
  },now);
  assert.equal(retained.status,'resolved');assert.equal(retained.receipt.id,id);
  assert.equal(retained.receipt.payload_sha256,data.row.payload_sha256);
});

test('missing, ambiguous or failed prediction reads cannot fall back to snapshots or leak errors',async()=>{
  const data=fixture();
  for(const rows of [[],[data.row,data.row],null,{rows:[data.row]}]) {
    let calls=0;
    const result=await resolveImmutableForecast(data.request,async()=>{calls++;return rows;},now);
    assert.deepEqual(result,{status:'unavailable',reason:'prediction_unavailable'});assert.equal(calls,1);
  }
  const result=await resolveImmutableForecast(data.request,async()=>{throw Error('PRIVATE_DATABASE_DETAILS');},now);
  assert.deepEqual(result,{status:'unavailable',reason:'prediction_unavailable'});
  assert.equal(JSON.stringify(result).includes('PRIVATE_DATABASE_DETAILS'),false);
});

test('legacy missing receipts, mismatched identities and exact TEXT hash failures remain unavailable',async()=>{
  const data=fixture();
  for(const patch of [{recorded_at:null,payload_sha256:null},{id:'b'.repeat(64)},
    {payload_sha256:'b'.repeat(64)},{payload:JSON.stringify(JSON.parse(data.row.payload))},
    {recorded_at:new Date('2026-10-14T17:00:00Z')}]) {
    const {result,calls}=await resolve({...data,row:{...data.row,...patch}});
    assert.deepEqual(result,{status:'unavailable',reason:'receipt_unavailable'});assert.equal(calls.length,1);
    assert.deepEqual(Object.keys(result).sort(),['reason','status']);
  }
});

test('a valid pregame capture and DB receipt within the kickoff millisecond retain their original precision',async()=>{
  const data=fixture({game_start_time:'2026-10-14T17:00:00.000900+00:00'});
  assert.equal(Date.parse(raw.captured_at),Date.parse(data.row.recorded_at));
  assert.equal(Date.parse(raw.captured_at),Date.parse(JSON.parse(data.row.payload).game_start_time));
  const {result}=await resolve(data);
  assert.equal(result.status,'resolved');assert.equal(result.receipt.recorded_at,data.row.recorded_at);
  assert.equal(result.context.captured_at,raw.captured_at);
});

test('same-millisecond forward chronology violations cannot pass through JavaScript rounding',async()=>{
  for(const patch of [
    {quote_time:'2026-10-14T17:00:00.000350+00:00'},
    {history_observed_before:'2026-10-14T17:00:00.000450+00:00'},
    {model_generated_at:'2026-10-14T17:00:00.000550+00:00'},
    {history_observed_before:'2026-10-14T17:00:00.000550+00:00'},
    {availability:{...raw.availability,captured_at:'2026-10-14T17:00:00.000550+00:00'}}]) {
    const {result}=await resolve(fixture(patch));
    assert.deepEqual(result,{status:'unavailable',reason:'chronology_unavailable'});
  }
  const {result}=await resolve(fixture({},'2026-10-14T17:00:00.000450Z'));
  assert.deepEqual(result,{status:'unavailable',reason:'chronology_unavailable'});
});

test('capture-to-receipt equality is valid while a receipt exactly at kickoff is unavailable',async()=>{
  const equal=await resolve(fixture({},'2026-10-14T17:00:00.000500Z'));
  assert.equal(equal.result.status,'resolved');
  const late=await resolve(fixture({game_start_time:'2026-10-14T17:00:00.000600+00:00'}));
  assert.deepEqual(late.result,{status:'unavailable',reason:'chronology_unavailable'});
});

test('future clock tolerance retains the current millisecond but rejects the next one',async()=>{
  const clock=Date.parse('2026-10-14T17:00:00Z');
  const boundary=await resolve(fixture({},'2026-10-14T17:01:00.000999Z'),clock);
  assert.equal(boundary.result.status,'resolved');
  const beyond=await resolve(fixture({},'2026-10-14T17:01:00.001000Z'),clock);
  assert.deepEqual(beyond.result,{status:'unavailable',reason:'chronology_unavailable'});
});

test('original source offsets and long retained athlete labels survive exact ID-based query preparation',async()=>{
  const source='2026-10-14T12:00:00.000300-05:00';
  const data=fixture({history_observed_before:source,player:'Synthetic '.repeat(10)});
  const {result}=await resolve(data);assert.equal(result.status,'resolved');
  assert.equal(result.context.player,JSON.parse(data.row.payload).player);
  assert.equal(result.context.history_observed_before,source);assert.equal(result.query.args[6],source);
  assert.equal(result.query.args[1],'');assert.equal(result.query.args[5],raw.player_id);
});

test('legacy descriptive source scope remains capture-time even when generation precedes capture',async()=>{
  const data=fixture({model_version:'empirical-jeffreys-v4',history_policy_version:undefined,
    history_observed_before:'2026-10-14T17:00:00.000200+00:00'});
  const {result}=await resolve(data);assert.equal(result.status,'resolved');
  assert.equal(result.query.args[6],raw.captured_at);
  assert.equal(result.context.captured_at,raw.captured_at);
});

test('known policies require their original cutoff and source metadata rather than guessed fields',async()=>{
  for(const patch of [{history_policy_version:undefined},{history_policy_version:'wrong-policy'},
    {history_observed_before:undefined},{forecast_cutoff:undefined},{forecast_cutoff:'2026-02-30'},
    {player_id:undefined},{player_id:'other-athlete'}]) {
    const {result}=await resolve(fixture(patch));
    assert.deepEqual(result,{status:'unavailable',reason:'history_context_unavailable'});
  }
});

test('array-coerced sport, prop and availability status cannot become a retained history context',async()=>{
  for(const patch of [{sport:['nfl']},{prop_type:['pass_yds']},
    {availability:{...raw.availability,status:['observed'],roster_confirmed:false}}]) {
    const {result}=await resolve(fixture(patch));
    assert.deepEqual(result,{status:'unavailable',reason:'history_context_unavailable'});
  }
});

test('all supported sports keep the original private as-of history source and stable athlete identity',async()=>{
  for(const [sport,version,policy,playerId,prop,view] of [
    ['nba','empirical-jeffreys-v4-nba-source-asof-v1','nba-source-asof-v1','123','points','dashboard_gamelogs_asof'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','receptions','dashboard_gamelog_versions'],
    ['nfl','empirical-jeffreys-v4-nfl-history-v1','nfl-explicit-receiving-v1','00-0000001','rush_yds','dashboard_nfl_core_gamelogs_asof'],
    ['cfb','empirical-jeffreys-v4-cfb-history-v1','cfb-explicit-receiving-v1','123','rec_yds','dashboard_gamelog_versions']]) {
    const {result}=await resolve(fixture({sport,model_version:version,history_policy_version:policy,player_id:playerId,prop_type:prop}));
    assert.equal(result.status,'resolved');assert.ok(result.query.sql.includes(view));
    assert.deepEqual(result.query.args,[sport,'',20,raw.forecast_cutoff,true,playerId,raw.history_observed_before]);
  }
});
