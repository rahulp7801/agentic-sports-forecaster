import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fetchForecasts} from '../lib/fetchForecasts.ts';
import {canonicalForecastDisplayJson,FORECAST_RECORD_BINDING_PROTOCOL} from '../lib/forecastDisplayPacket.ts';
import {FORECAST_DISPLAY_PROTOCOL} from '../lib/forecastDisplayAuthority.ts';

// Synthetic display output, independent of private forecasts and selection rules.
const now=Date.parse('2026-10-14T02:00:00Z'),stamp=new Date(now).toISOString(),revision='a'.repeat(64);
const base={id:'A',player:'Player A',team:'KC',opponent:'BUF',home_team:'Home',away_team:'Away',
  game_id:'game',sport:'nfl',prop_type:'pass_yds',line:249.5,direction:'over',true_prob:.75,
  implied_prob:.5,ev_pct:.25,expected_return:.5,push_probability:0,confidence_interval:[.6,.85],
  model_version:'synthetic-display-version',game_start_time:new Date(now+2*3600000).toISOString(),
  kelly_fraction:.02,american_odds:100,sportsbook:'draftkings',trade_plan:[],injury_flags:{},
  market_type:'player_pass_yds',snapped_at:stamp,captured_at:stamp,strength:'unrated',gated:false,
  sample_size:40,mean_stat:260};

function requestFor(url) {
  const params=new URL(url,'https://example.test').searchParams;
  return {sport:params.get('sport'),view:params.get('view') ?? 'library',offset:Number(params.get('offset') ?? 0),
    limit:Number(params.get('limit') ?? 100),revision:params.get('revision'),player:params.get('player') ?? ''};
}

function packet(request,signals,options={}) {
  const complete=options.complete ?? true,invalid=options.invalid ?? 0,version=options.revision ?? revision;
  const rows=signals.map((signal,index)=>{
    const library=request.view==='library',live=request.view==='qualified';
    const primary=options.primaryIndices?.[index] ?? index;
    const deadline=options.deadlines?.[index] ?? now+300001;
    const lock=Date.parse(signal.game_start_time)-3600000;
    return {row_index:index,id:signal.id,state:library ? 'research' : live ? 'live' : 'watchlist',
      gated:signal.gated,gate_reason:signal.gate_reason ?? null,role:library ? 'library' : primary===index ? 'primary' : 'alternative',
      primary_index:library ? null : primary,group_rank:library ? null : options.ranks?.[index] ?? index,
      actionable_until:live ? new Date(deadline).toISOString() : null,
      visible_until:library ? null : new Date(live ? deadline : lock).toISOString(),lock_at:new Date(lock).toISOString()};
  });
  const payload={search_player:request.player,generated_at:stamp,games:[],signals,
    display:{protocol:FORECAST_DISPLAY_PROTOCOL,evaluated_at:stamp,revision:version,view:request.view,
      complete,invalid_signals:invalid,rows},invalid_signals:invalid,
    total_count:options.total ?? request.offset+signals.length,
    pagination:{offset:request.offset,next_offset:complete || request.view!=='library' ? null : options.next ?? request.offset+signals.length,
      revision:version,complete},research_window:'Synthetic display test window'};
  return bind(payload,request);
}

function bind(payload,request,resource='signals') {
  const normalized=JSON.parse(JSON.stringify(payload));
  const preimage={protocol:FORECAST_RECORD_BINDING_PROTOCOL,resource,request,payload:normalized};
  return {...normalized,binding:{protocol:FORECAST_RECORD_BINDING_PROTOCOL,resource,request,
    payload_sha256:createHash('sha256').update(canonicalForecastDisplayJson(preimage)).digest('hex')}};
}

const response=body=>({ok:true,json:async()=>body});

test('qualified fetching preserves supplied primaries and alternatives without private reranking',async t=>{
  t.mock.method(Date,'now',()=>now);
  const values=[base,{...base,id:'ALT',line:250.5},
    {...base,id:'B',player:'Player B',true_prob:.9,confidence_interval:[.8,.95],expected_return:.8,ev_pct:.4}];
  const fetchImpl=async url=>response(packet(requestFor(url),values,{primaryIndices:[0,0,2],ranks:[0,0,1]}));
  const primaries=await fetchForecasts('nfl',undefined,'qualified',fetchImpl);
  const alternatives=await fetchForecasts('nfl',undefined,'qualified',fetchImpl,1000,undefined,true);
  assert.deepEqual(primaries.signals.map(row=>row.id),['A','B']);
  assert.deepEqual(alternatives.signals.map(row=>row.id),['A','ALT','B']);
  assert.equal(primaries.signals[0].model_version,'synthetic-display-version');
  assert.equal(primaries.signals[0].true_prob,.75);
});

test('same-ID changes to prices, lines, metrics or game time reject the entire bound packet',async t=>{
  t.mock.method(Date,'now',()=>now);
  for(const patch of [{american_odds:101},{line:250.5},{true_prob:.7},{implied_prob:.51},{ev_pct:.24},
    {expected_return:.4},{confidence_interval:[.61,.85]},{kelly_fraction:.01},{sample_size:41},
    {game_start_time:new Date(now+3*3600000).toISOString()}]) {
    await assert.rejects(fetchForecasts('nfl',undefined,'qualified',async url=>{
      const body=packet(requestFor(url),[base]);Object.assign(body.signals[0],patch);
      assert.equal(body.signals[0].id,'A');return response(body);
    }),/binding|coverage/);
  }
});

test('bound display ordering, lifetime and coverage cannot be changed separately from the packet',async t=>{
  t.mock.method(Date,'now',()=>now);
  for(const mutate of [
    body=>{body.display.rows[0].actionable_until=new Date(now+350000).toISOString();body.display.rows[0].visible_until=body.display.rows[0].actionable_until;},
    body=>{body.display.rows[0].group_rank=1;},
    body=>{body.display.complete=false;},
    body=>{body.invalid_signals=1;},
    body=>{delete body.signals[0].gated;}]) {
    await assert.rejects(fetchForecasts('nfl',undefined,'qualified',async url=>{
      const body=packet(requestFor(url),[base]);mutate(body);return response(body);
    }),/binding|coverage/);
  }
});

test('a matching digest for another resource, sport or request still cannot supply forecasts',async t=>{
  t.mock.method(Date,'now',()=>now);
  for(const mutation of [
    (body,request)=>bind(body,request,'picks'),
    (body,request)=>bind(body,{...request,sport:'nba'}),
    (body,request)=>bind(body,{...request,view:'library'}),
    (body,request)=>bind(body,{...request,limit:99})]) {
    await assert.rejects(fetchForecasts('nfl',undefined,'qualified',async url=>{
      const request=requestFor(url),{binding,...payload}=packet(request,[base]);void binding;
      return response(mutation(payload,request));
    }),/binding|coverage/);
  }
});

test('a valid digest cannot replace required record flags, finite metrics or consistent authority fields',async t=>{
  t.mock.method(Date,'now',()=>now);
  for(const patch of [{gated:undefined},{gated:'false'},{true_prob:NaN},{american_odds:100.5}]) {
    await assert.rejects(fetchForecasts('nfl',undefined,'qualified',async url=>
      response(packet(requestFor(url),[{...base,...patch}]))),/binding|coverage/);
  }
  for(const mutate of [body=>{body.display.complete=false;},
    body=>{body.display.rows[0].role='alternative';},body=>{body.display.rows[0].state='watchlist';}]) {
    await assert.rejects(fetchForecasts('nfl',undefined,'qualified',async url=>{
      const request=requestFor(url),{binding,...payload}=packet(request,[base]);void binding;
      mutate(payload);return response(bind(payload,request));
    }),/binding|coverage/);
  }
});

test('source-age equality is visible for one final millisecond and an expired primary hides its alternatives',async t=>{
  let clock=now;t.mock.method(Date,'now',()=>clock);
  const values=[base,{...base,id:'ALT',line:250.5},{...base,id:'B',player:'Player B'}];
  const fetchImpl=async url=>response(packet(requestFor(url),values,{primaryIndices:[0,0,2],ranks:[0,0,1],
    deadlines:[now+300001,now+500000,now+500000]}));
  clock=now+300000;
  assert.deepEqual((await fetchForecasts('nfl',undefined,'qualified',fetchImpl,1000,undefined,true)).signals.map(row=>row.id),['A','ALT','B']);
  clock=now+300001;
  assert.deepEqual((await fetchForecasts('nfl',undefined,'qualified',fetchImpl,1000,undefined,true)).signals.map(row=>row.id),['B']);
});

test('T-60 equality and incomplete or invalid qualified coverage withhold actions',async t=>{
  let clock=now;t.mock.method(Date,'now',()=>clock);
  const locking={...base,game_start_time:new Date(now+3601000).toISOString()};
  const fetchImpl=async url=>response(packet(requestFor(url),[locking],{deadlines:[now+1000]}));
  clock=now+999;assert.equal((await fetchForecasts('nfl',undefined,'qualified',fetchImpl)).signals.length,1);
  clock=now+1000;assert.deepEqual((await fetchForecasts('nfl',undefined,'qualified',fetchImpl)).signals,[]);
  clock=now;
  for(const options of [{complete:false,total:5002},{invalid:1}]) {
    const result=await fetchForecasts('nfl',undefined,'qualified',async url=>response(packet(requestFor(url),[base],options)));
    assert.deepEqual(result.signals,[]);assert.equal(result.complete,false);
  }
});

test('expired watchlist prices stay descriptive until T-60 and never acquire a live classification',async t=>{
  let clock=now;t.mock.method(Date,'now',()=>clock);
  const stale={...base,gated:true,gate_reason:'stale_quote',snapped_at:new Date(now-600000).toISOString()};
  const fetchImpl=async url=>response(packet(requestFor(url),[stale]));
  const research=await fetchForecasts('nfl',undefined,'candidates',fetchImpl);
  assert.equal(research.signals.length,1);assert.equal(research.signals[0].gated,true);
  assert.equal(research.signals[0].gate_reason,'stale_quote');
  clock=now+3600000;
  assert.deepEqual((await fetchForecasts('nfl',undefined,'candidates',fetchImpl)).signals,[]);
});

test('verified library pages retain exact continuation and partial coverage after a later failure',async()=>{
  for(const failure of [503,'timeout']) {
    let calls=0;const requests=[];
    const result=await fetchForecasts('nfl',undefined,'library',async url=>{
      const request=requestFor(url);requests.push(request);
      if(calls++>0) {
        if(failure==='timeout') throw new DOMException('Timed out','TimeoutError');
        return {ok:false,status:failure};
      }
      return response(packet(request,Array.from({length:100},(_,index)=>({...base,id:'record-'+index})),
        {complete:false,total:240,next:100}));
    });
    assert.equal(result.signals.length,100);assert.equal(result.total_count,240);assert.equal(result.complete,false);
    assert.deepEqual(result.cursor,{offset:100,revision,total_count:240});
    assert.deepEqual(requests.map(request=>[request.offset,request.revision]),[[0,null],[100,revision]]);
  }
});

test('library search and revision changes cannot swap an already loaded research page',async()=>{
  let page=0;
  await assert.rejects(fetchForecasts('nfl',undefined,'library',async url=>{
    const request=requestFor(url);
    return response(packet(request,[{...base,player:'Player A'}],{complete:false,total:3,next:request.offset+1,
      revision:page++===0 ? revision : 'b'.repeat(64)}));
  },1000,undefined,false,'Player'),/coverage/);
  await assert.rejects(fetchForecasts('nfl',undefined,'library',async url=>response(packet(requestFor(url),
    [{...base,player:'Other Name'}])),1000,undefined,false,'Player'),/searched/);
});

test('unsigned packets fail closed on every view and cancellation never returns retained research',async()=>{
  for(const view of ['library','qualified','candidates']) {
    await assert.rejects(fetchForecasts('nfl',undefined,view,async url=>{
      const {binding,...body}=packet(requestFor(url),view==='candidates' ? [{...base,gated:true,gate_reason:'stale_quote'}] : [base]);
      void binding;return response(body);
    }),/coverage/);
  }
  const controller=new AbortController();let calls=0;
  await assert.rejects(fetchForecasts('nfl',controller.signal,'library',async url=>{
    if(calls++>0) {controller.abort();throw new DOMException('Canceled','AbortError');}
    return response(packet(requestFor(url),[base],{complete:false,total:2,next:1}));
  }),{name:'AbortError'});
});
