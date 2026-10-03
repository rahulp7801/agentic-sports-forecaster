import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import {readSignalDisplay,readSignalDisplaySnapshots} from '../lib/signalDisplay.ts';
import {publicSignalSnapshots} from '../lib/signalMetrics.ts';
import {forecastPage,forecastRequest} from '../lib/forecastPage.ts';
import {base,now} from './fixtures/qualifiedSignal.mjs';

const stamp=new Date(now).toISOString();
const serial=value=>JSON.parse(JSON.stringify(value));
function rawSignal(sport='nfl') {
  const football=sport==='cfb'?'college-football':'nfl',player_id=sport==='nfl'?'00-0000001':'4429000';
  const roster=sport==='nba' ? 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/13/roster'
    : `https://site.api.espn.com/apis/site/v2/sports/football/${football}/teams/12/roster`;
  const source=sport==='nba' ? 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
    : `https://site.api.espn.com/apis/site/v2/sports/football/${football}/injuries`;
  return {...base,sport,player_id,prop_type:sport==='nba'?'points':'pass_yds',
    availability:{...base.availability,source_url:source,roster_source_url:roster,
      player_id:'4429000',player_image_url:`https://a.espncdn.com/i/headshots/${sport==='cfb'?'college-football':sport}/players/full/4429000.png`}};
}
function richSignal() {
  const signal=rawSignal(),source=signal.availability.source_url;
  const report={player:'Defender',status:'Questionable',position:'CB',reported_at:stamp,
    team:'BUF',relationship:'opponent',unit:'defense',source_url:source,source_sha256:'d'.repeat(64)};
  const sample_window={cutoff:'2026-09-10',active:{oldest:'2026-08-25',newest:'2026-09-08'},
    absent:null,unknown:{oldest:'2026-09-05',newest:'2026-09-05'}};
  const active={games:2,mean:-1.25,hit_rate:.5},absent={games:0,mean:null,hit_rate:null};
  const split={player:report.player,status:report.status,position:report.position,team:report.team,
    relationship:report.relationship,unit:report.unit,source:'nflverse_snap_counts',participation:'recorded unit snaps',
    evidence_version:'recorded-participation-v3',unknown_games:1,active,absent,sample_window,
    recent_window:{version:'participation-recent-30d-v1',since:'2026-08-11',cutoff:'2026-09-10',
      active,absent,unknown_games:1,sample_window}};
  return {...signal,availability:{...signal.availability,opponent_team:'BUF',opponent_injury_coverage:'observed',
    teammates:[report],context_splits:[split]},
    player_profile:{player:signal.player,name:signal.player,team:'KC',player_id:'4429000',
      image_url:signal.availability.player_image_url,captured_at:stamp,
      source_url:signal.availability.roster_source_url,source_sha256:'f'.repeat(64),jersey:'10',position:'QB'},
    next_gen_stats:{status:'observed',evidence_version:'ngs-row-commitment-v2',stat_type:'passing',
      sample_weeks:2,cutoff_season:2026,cutoff_week:2,cutoff_exclusive:true,
      metrics:{avg_time_to_throw:2.71,aggressiveness:13.4},source_provider:'nflverse_ngs',
      source_url:'https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_passing.parquet',
      source_sha256:'c'.repeat(64),source_observed_at:stamp,observed_before:stamp,probability_adjusted:false,
      sample_periods:[{season:2025,week:2,team:'KC'},{season:2025,week:1,team:null}],roster_team:'KC'}};
}
function approved(raw=rawSignal(),clock=now) {
  return serial(publicSignalSnapshots([{generated_at:stamp,games:[],signals:[raw]}],clock).signals[0]);
}
function page(raw,view,sport=raw.sport) {
  const game={game_id:raw.game_id,home_team:raw.home_team,away_team:raw.away_team,sport,date:'20260910'};
  const input={rows:[{payload:{generated_at:stamp,games:[game],signals:[raw]}}],profiles:{},
    total_count:1,revision:'a'.repeat(64),metadata:{generated_at:stamp,games:[],signals:[]},
    invalid_envelopes:0,window_complete:true};
  const request=forecastRequest(new URL(`https://example.test/api/signals?sport=${sport}&view=${view}`));
  return serial(forecastPage(input,request,now));
}

test('real producer outputs across sports, gates and null evidence round-trip exactly',()=>{
  for(const sport of ['nfl','nba','cfb']) for(const patch of [
    {},{gated:true,gate_reason:'risk_gate'},{snapped_at:new Date(now-3600000).toISOString()},
    {confidence_interval:null},{availability:{status:'unavailable'}},{mean_stat:-1.25},
  ]) {
    const record=approved({...rawSignal(sport),...patch});
    assert.ok(record,`${sport} producer record missing`);
    assert.deepEqual(readSignalDisplay(record),record,`${sport} ${JSON.stringify(patch)}`);
  }
  const legacy=approved(rawSignal(),now+60*86400000);
  assert.equal(legacy.expected_return,null);assert.equal(legacy.confidence_interval,null);
  assert.deepEqual(readSignalDisplay(legacy),legacy);
});

test('actual complete forecast pages for every view and sport keep serialized output parity',()=>{
  for(const sport of ['nfl','nba','cfb']) for(const view of ['library','qualified','candidates']) {
    const raw=rawSignal(sport);
    if(view==='candidates') raw.snapped_at=new Date(now-360000).toISOString();
    const result=page(raw,view,sport),projected=readSignalDisplaySnapshots([result],sport);
    assert.equal(result.signals.length,1,`${sport}/${view} fixture has no selected row`);
    assert.deepEqual(projected,{generated_at:result.generated_at,games:result.games,
      signals:result.signals,invalid_signals:0},`${sport}/${view}`);
  }
  for(const view of ['library','qualified','candidates']) {
    const raw=richSignal();if(view==='candidates') raw.snapped_at=new Date(now-360000).toISOString();
    const result=page(raw,view),projected=readSignalDisplaySnapshots([result],'nfl');
    assert.ok(result.signals[0].availability.context_splits[0].recent_window);
    assert.ok(result.signals[0].next_gen_stats.sample_periods);
    assert.ok(result.signals[0].player_profile);
    assert.deepEqual(projected.signals,result.signals);
  }
  const empty=serial(forecastPage({rows:[],profiles:{},total_count:0,revision:'a'.repeat(64),metadata:null,
    invalid_envelopes:0,window_complete:true},forecastRequest(new URL('https://example.test/api/signals?sport=nfl')),now));
  assert.equal(empty.generated_at,null);
  assert.deepEqual(readSignalDisplaySnapshots([empty],'nfl'),{generated_at:null,games:[],signals:[],invalid_signals:0});
});

test('supplied metrics, opaque versions and held decisions are never reconstructed',()=>{
  const supplied={...approved(),model_version:'opaque-model-version',history_policy_version:'opaque-history-policy',
    history_source_admission_policy:'opaque-source-policy',history_source_verified:false,
    true_prob:.123,implied_prob:.777,ev_pct:.231,expected_return:-5.55,confidence_interval:[.01,.99],
    kelly_fraction:.75,gated:true,gate_reason:'opaque held decision'};
  assert.deepEqual(readSignalDisplay(supplied),supplied);
  assert.equal(readSignalDisplay(supplied).gated,true);
  const context=approved(richSignal());
  context.next_gen_stats.evidence_version='opaque-tracking-version';
  context.availability.context_splits[0].evidence_version='opaque-participation-version';
  context.availability.context_splits[0].recent_window.version='opaque-recent-version';
  assert.deepEqual(readSignalDisplay(context),context);
});

test('unapproved fields at every layer are omitted and copied evidence cannot mutate its input',()=>{
  const input=approved(richSignal()),secret='private payload never copied';
  input.parameters=secret;input.board_state='locked';input.profit_claim=secret;
  input.availability.parameters=secret;input.availability.teammates[0].parameters=secret;
  input.availability.context_splits[0].parameters=secret;
  input.availability.context_splits[0].active.parameters=secret;
  input.availability.context_splits[0].sample_window.active.parameters=secret;
  input.availability.context_splits[0].recent_window.parameters=secret;
  input.next_gen_stats.partition_refs=secret;input.next_gen_stats.sample_periods[0].parameters=secret;
  input.player_profile.parameters=secret;
  const output=readSignalDisplay(input);
  assert.ok(output);assert.equal(JSON.stringify(output).includes(secret),false);
  assert.equal(output.board_state,undefined);
  output.availability.teammates[0].player='Changed';output.confidence_interval[0]=0;
  output.next_gen_stats.metrics.avg_time_to_throw=99;
  assert.equal(input.availability.teammates[0].player,'Defender');assert.notEqual(input.confidence_interval[0],0);
  assert.equal(input.next_gen_stats.metrics.avg_time_to_throw,2.71);
});

test('malformed scalar fields, approval flags and optional outputs are rejected without coercion',()=>{
  const input=approved();
  for(const patch of [{id:''},{player:'bad\nname'},{sport:{toString:()=> 'nfl'}},{prop_type:'unknown'},
    {true_prob:'0.65'},{implied_prob:NaN},{expected_return:Infinity},{sample_size:1.5},
    {mean_stat:'0'},{kelly_fraction:-.1},{american_odds:99},{confidence_interval:[.7,.6]},
    {confidence_interval:[.5]},{trade_plan:Array(4).fill('text')},{injury_flags:{x:5}},
    {gated:undefined},{gated:null},{gated:0},{gated:'false'},{history_source_verified:'true'},
    {history_policy_version:'x'.repeat(65)},{captured_at:'2026-09-10'},{forecast_cutoff:'2026-02-30'},
    {availability:null},{player_profile:{}},{next_gen_stats:{}}]) {
    assert.equal(readSignalDisplay({...input,...patch}),null,JSON.stringify(patch));
  }
  const accessor={...input};Object.defineProperty(accessor,'gated',{enumerable:true,get(){throw Error('must not execute');}});
  assert.equal(readSignalDisplay(accessor),null);
  const sparse={...input,trade_plan:new Array(1)};assert.equal(readSignalDisplay(sparse),null);
  let accessed=0;
  for(const malformed of [
    ()=>{const value=['text'];Object.defineProperty(value,0,{enumerable:true,get(){accessed++;return 'text';}});return value;},
    ()=>{const value=['text'];Object.defineProperty(value,0,{enumerable:false,value:'text'});return value;},
    ()=>{const value=['text'];value[Symbol('private')]='secret';return value;},
    ()=>{const value=['text'];Object.defineProperty(value,'private',{enumerable:false,value:'secret'});return value;},
    ()=>{const value=['text'];value.extra='secret';return value;},
  ]) assert.equal(readSignalDisplay({...input,trade_plan:malformed()}),null);
  assert.equal(accessed,0,'Array value getters must never execute');
  for(const key of Object.keys(input)) {
    if(['player_id','captured_at','availability','forecast_cutoff','history_policy_version',
      'history_observed_before','history_source_admission_policy','history_source_verified','gate_reason'].includes(key)) continue;
    const missing={...input};delete missing[key];assert.equal(readSignalDisplay(missing),null,`Missing ${key}`);
  }
});

test('malformed nested evidence is rejected while nullable cohort fields remain intact',()=>{
  const input=approved(richSignal());
  for(const mutate of [
    value=>{value.availability.probability_adjusted=true;},
    value=>{delete value.availability.source_url;},
    value=>{value.availability.teammates[0].source_url='javascript:alert(1)';},
    value=>{value.availability.context_splits[0].active.games='2';},
    value=>{value.availability.context_splits[0].sample_window.active.newest='2026-02-30';},
    value=>{value.availability.context_splits[0].recent_window.active.mean=NaN;},
    value=>{value.next_gen_stats.metrics.unknown_metric=1;},
    value=>{value.next_gen_stats.sample_periods[0].week='1';},
    value=>{value.next_gen_stats.source_sha256='not-a-hash';},
    value=>{value.player_profile.image_url='https://user:password@example.test/a.png';},
  ]) {
    const changed=structuredClone(input);mutate(changed);assert.equal(readSignalDisplay(changed),null);
  }
  const output=readSignalDisplay(input);
  assert.deepEqual(output.availability.context_splits[0].absent,{games:0,mean:null,hit_rate:null});
  assert.equal(output.availability.context_splits[0].sample_window.absent,null);
  assert.equal(output.next_gen_stats.sample_periods[1].team,null);
});

test('snapshot bounds, matching game receipts, filtering and invalid counts remain explicit',()=>{
  const nfl=approved(),nba=approved(rawSignal('nba'));
  const game={game_id:'game',home_team:'Home',away_team:'Away',date:'20260910',sport:'nfl'};
  const first={generated_at:stamp,signals:[nfl,{...nfl,gated:undefined},nba],games:[game]};
  const later=new Date(now+1000).toISOString();
  const result=readSignalDisplaySnapshots([first,{generated_at:later,signals:[nfl],games:[game]}],'nfl');
  assert.equal(result.generated_at,later);assert.equal(result.invalid_signals,1);
  assert.deepEqual(result.signals,[nfl,nfl]);assert.deepEqual(result.games,[game]);
  assert.deepEqual(readSignalDisplaySnapshots([]),{generated_at:null,games:[],signals:[],invalid_signals:0});
  assert.deepEqual(readSignalDisplaySnapshots([{generated_at:null,signals:[],games:[]}]),
    {generated_at:null,games:[],signals:[],invalid_signals:0});
  assert.throws(()=>readSignalDisplaySnapshots([{generated_at:null,signals:[nfl],games:[]}]));
  assert.throws(()=>readSignalDisplaySnapshots([first,{...first,games:[{...game,home_team:'Different'}]}]));
  assert.throws(()=>readSignalDisplaySnapshots([{...first,games:[{...game,date:'20260230'}]}]));
  assert.throws(()=>readSignalDisplaySnapshots(Array(101).fill(first)));
  assert.throws(()=>readSignalDisplaySnapshots([{generated_at:stamp,signals:Array(5001).fill(nfl),games:[]}]));
  assert.throws(()=>readSignalDisplaySnapshots([{generated_at:stamp,signals:Array(3000).fill(nfl),games:[]},
    {generated_at:stamp,signals:Array(2001).fill(nfl),games:[]}]));
  const games=Array.from({length:100},(_,index)=>({...game,game_id:'game-'+index}));
  assert.equal(readSignalDisplaySnapshots([{generated_at:stamp,signals:[],games}]).games.length,100);
  assert.throws(()=>readSignalDisplaySnapshots([{generated_at:stamp,signals:[],games:[...games,{...game,game_id:'extra'}]}]));
});

test('the public signal projection depends only on public type declarations, including type imports',()=>{
  const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
  const reviewed=new Set(['lib/signalDisplay.ts','lib/types.ts']),visited=new Set(),queue=['lib/signalDisplay.ts'];
  while(queue.length) {
    const name=queue.shift();if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed signal projection source: '+name);visited.add(name);
    const file=path.join(frontend,name),source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
    function inspect(node) {
      let specifier;
      if(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)) specifier=node.moduleSpecifier;
      if(ts.isImportEqualsDeclaration(node)&&ts.isExternalModuleReference(node.moduleReference)) specifier=node.moduleReference.expression;
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed signal projection import');specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {assert.ok(ts.isLiteralTypeNode(node.argument));specifier=node.argument.literal;}
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier));const target=specifier.text;
        assert.ok(target.startsWith('.'),'Unexpected signal projection package import: '+target);
        const base=path.resolve(path.dirname(file),target),resolved=[base,base+'.ts'].find(value=>fs.existsSync(value));
        assert.ok(resolved,'Unresolved signal projection import');queue.push(path.relative(frontend,resolved).split(path.sep).join('/'));
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  assert.deepEqual([...visited].sort(),[...reviewed].sort());
});
