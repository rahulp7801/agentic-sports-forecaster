import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import {FORECAST_HISTORY_DISPLAY_PROTOCOL,readForecastHistoryDisplay} from '../lib/forecastHistoryDisplay.ts';

const subject={forecast_id:'synthetic-forecast',forecast_record_sha256:'a'.repeat(64),sport:'nfl',
  player:'Synthetic Athlete',player_id:'00-0000001',prop_type:'receptions',line:4.5,direction:'over'};
const scope={captured_at:'2026-10-04T03:01:00Z',game_date_before:'2026-10-04',
  source_observed_before:'2026-10-04T03:00:10Z',source_cutoff_kind:'model_selection'};
const expected={revision:'b'.repeat(64),subject,scope};
const rows=[
  {date:'2026-10-03',team:'BUF',opponent:'DET',stat:7,outcome:'Matched direction'},
  {date:'2026-10-02',team:'BUF',opponent:'DET',stat:4.5,outcome:'Tie'},
  {date:'2026-10-01',team:'BUF',opponent:'DET',stat:null,outcome:'Missing stat'},
];
const window={rows,wins:1,losses:0,ties:1,missing:1,decided:1,rate:1,mean:5.75};
const summary={games:3,observed:2,missing:1,mean:5.75,wins:1,decided:1,rate:1,
  newest:'2026-10-03',newestObserved:'2026-10-03',oldest:'2026-10-01',teams:['BUF']};
const emptySummary={games:0,observed:0,missing:0,mean:null,wins:0,decided:0,rate:null,
  newest:null,newestObserved:null,oldest:null,teams:[]};
function available() {
  return JSON.parse(JSON.stringify({protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:'opaque-producer-v17',...expected,
    status:'available',source_coverage:'bounded_as_of_records',windows:{'10':window,'20':window},
    recent:{recent:summary,previous:emptySummary,daysBeforeForecast:1,observedDaysBeforeForecast:1,meanChange:null},
    calendar:{from:'2026-09-04',before:'2026-10-04',allTeams:summary,capturedTeam:'BUF',
      capturedTeamSample:summary,limitedToLatest20:false},
    card_summary:'Synthetic recorded-team form. This does not change the forecast probability.',
    context_labels:[{player:'Synthetic Defender',team:'DET',relationship:'opponent',unit:'defense',
      window:['Recorded participation: 2026-09-01 to 2026-09-30.'],recent:'Supplied descriptive participation summary.'}]}));
}

test('bounded descriptive outputs round-trip and cannot mutate their source',()=>{
  const input=available(),output=readForecastHistoryDisplay(input,expected);
  assert.deepEqual(output,input);
  output.windows['10'].rows[0].stat=99;output.calendar.allTeams.teams.push('OTHER');
  output.context_labels[0].window[0]='Changed';
  assert.equal(input.windows['10'].rows[0].stat,7);assert.deepEqual(input.calendar.allTeams.teams,['BUF']);
  assert.notEqual(input.context_labels[0].window[0],'Changed');
  const supplied=available();supplied.producer_version='a-different-opaque-version';
  supplied.windows['10'].mean=-1.25;supplied.windows['20'].mean=-1.25;
  supplied.recent.recent.rate=.123;
  assert.deepEqual(readForecastHistoryDisplay(supplied,expected),supplied,'Descriptive values must not be recalculated');
});

test('revision, full record commitment, identity, line and every original scope field must match',()=>{
  for(const mutate of [
    v=>{v.revision='c'.repeat(64);},v=>{v.subject.forecast_id='other';},
    v=>{v.subject.forecast_record_sha256='c'.repeat(64);},v=>{v.subject.player='Other Athlete';},
    v=>{v.subject.player_id='00-0000002';},v=>{v.subject.sport='nba';},
    v=>{v.subject.prop_type='pass_yds';},v=>{v.subject.line=5.5;},v=>{v.subject.direction='under';},
    v=>{v.scope.captured_at='2026-10-04T03:02:00Z';},v=>{v.scope.game_date_before='2026-10-05';},
    v=>{v.scope.source_observed_before='2026-10-04T03:00:20Z';},v=>{v.scope.source_cutoff_kind='forecast_capture';},
  ]) {const value=available();mutate(value);assert.equal(readForecastHistoryDisplay(value,expected),null);}
  assert.equal(readForecastHistoryDisplay(available()),null);
  assert.equal(readForecastHistoryDisplay(available(),null),null);
  assert.equal(readForecastHistoryDisplay(available(),{revision:expected.revision,subject}),null);
  const capture={...scope,source_observed_before:scope.captured_at,source_cutoff_kind:'forecast_capture'};
  const value=available();value.scope=capture;
  assert.ok(readForecastHistoryDisplay(value,{...expected,scope:capture}));
});

test('unavailable history can retain null scope but never expose stale summaries or live/settlement state',()=>{
  const unavailableScope={captured_at:null,game_date_before:null,source_observed_before:null,source_cutoff_kind:'unavailable'};
  const binding={...expected,scope:unavailableScope};
  const value={...available(),scope:unavailableScope,status:'unavailable',reason:'Original source cutoff is unavailable.',
    gated:false,board_state:'locked',result:'win',result_verified:true,actual_value:7};
  assert.deepEqual(readForecastHistoryDisplay(value,binding),{
    protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:value.producer_version,...binding,
    status:'unavailable',reason:value.reason});
  const hasNoHistory={...available(),scope:unavailableScope};
  assert.equal(readForecastHistoryDisplay(hasNoHistory,binding),null);
  for(const status of ['live','recorded','locked','final','unknown'])
    assert.equal(readForecastHistoryDisplay({...available(),status},expected),null);
});

test('unknown fields are omitted at each output layer and remain outside the public source closure',()=>{
  const input=available(),secret='private research omitted';
  input.parameters=secret;input.subject.parameters=secret;input.scope.parameters=secret;
  input.windows.parameters=secret;input.windows['10'].parameters=secret;
  input.windows['10'].rows[0].parameters=secret;input.windows['20'].rows[0].parameters=secret;
  input.recent.parameters=secret;input.recent.recent.parameters=secret;
  input.calendar.parameters=secret;input.calendar.capturedTeamSample.parameters=secret;
  input.context_labels[0].parameters=secret;
  input.gated=false;input.board_state='recorded';input.result_verified=true;
  const output=readForecastHistoryDisplay(input,expected);
  assert.ok(output);assert.equal(JSON.stringify(output).includes(secret),false);
  for(const field of ['gated','board_state','result_verified']) assert.equal(output[field],undefined);
});

test('strict calendars, no later source receipt and pre-cutoff rows preserve the descriptive window',()=>{
  for(const patch of [
    {captured_at:'2026-10-04T03:01:00'},
    {source_observed_before:'2026-10-04T03:01:01Z'},
    {source_observed_before:'2026-10-04T03:00:10+14:01'},
    {captured_at:'2026-02-30T03:01:00Z'},
    {game_date_before:'2026-02-30'},{game_date_before:'0000-10-04'},
  ]) {
    const badScope={...scope,...patch},value={...available(),scope:badScope};
    assert.equal(readForecastHistoryDisplay(value,{...expected,scope:badScope}),null);
  }
  for(const mutate of [
    v=>{v.windows['10'].rows[0].date='2026-10-04';},
    v=>{v.recent.recent.newestObserved='2026-10-04';},
    v=>{v.calendar.before='2026-10-05';},
    v=>{v.calendar.from='2026-10-04';},
    v=>{v.windows['10'].rows.reverse();},
    v=>{v.windows['10'].rows[0].team='OTHER';},
  ]) {const value=available();mutate(value);assert.equal(readForecastHistoryDisplay(value,expected),null);}
});

test('nonfinite values, coercions and malformed nullable samples fail closed',()=>{
  for(const mutate of [
    v=>{v.windows['10'].mean=NaN;},v=>{v.windows['20'].rows[0].stat=Infinity;},
    v=>{v.windows['10'].wins='1';},v=>{v.recent.recent.games=1.5;},
    v=>{v.calendar.allTeams.rate=1.1;},v=>{v.recent.meanChange=Infinity;},
    v=>{v.recent.daysBeforeForecast=-1;},v=>{v.windows['10'].rows[0].outcome='Win';},
    v=>{v.windows['10'].rows[0].stat=null;},v=>{v.calendar.limitedToLatest20='false';},
    v=>{v.calendar.capturedTeamSample=null;},v=>{delete v.card_summary;},
    v=>{v.context_labels[0].relationship='coach';},v=>{v.source_coverage='complete_census';},
  ]) {const value=available();mutate(value);assert.equal(readForecastHistoryDisplay(value,expected),null);}
  const unknownTeam=available();unknownTeam.calendar.capturedTeam=null;unknownTeam.calendar.capturedTeamSample=null;
  assert.ok(readForecastHistoryDisplay(unknownTeam,expected));
  const extreme=available();extreme.windows['10'].rows[0].stat=30000;extreme.windows['20'].rows[0].stat=30000;
  extreme.windows['10'].mean=30000;extreme.windows['20'].mean=30000;
  assert.ok(readForecastHistoryDisplay(extreme,expected),'Current PRA sums and signed differences remain representable');
});

test('supplied outcome labels, counts, nullable values and summary dates must agree without regrading stats',()=>{
  const emptyClaim=available();
  emptyClaim.windows['10']={rows:[],wins:10,losses:10,ties:10,missing:10,decided:10,rate:1,mean:42};
  assert.equal(readForecastHistoryDisplay(emptyClaim,expected),null,'Empty rows cannot publish nonzero claimed history');
  for(const mutate of [
    v=>{v.windows['10'].wins=0;},v=>{v.windows['10'].losses=1;},
    v=>{v.windows['10'].decided=0;},v=>{v.windows['10'].rate=null;},
    v=>{v.windows['10'].mean=null;},
    v=>{v.windows['10'].rows[0].outcome='Opposite direction';v.windows['20'].rows[0].outcome='Opposite direction';},
    v=>{v.recent.recent.observed=3;},v=>{v.recent.recent.decided=3;},
    v=>{v.recent.recent.wins=2;},v=>{v.recent.recent.rate=null;},
    v=>{v.recent.previous.mean=42;},v=>{v.recent.previous.rate=0;},
    v=>{v.recent.previous.newest='2026-09-01';},v=>{v.recent.previous.oldest='2026-09-01';},
    v=>{v.recent.previous.newestObserved='2026-09-01';},v=>{v.recent.previous.teams=['BUF'];},
    v=>{v.recent.recent.oldest=null;},v=>{v.recent.recent.newestObserved=null;},
    v=>{v.recent.recent.newestObserved='2026-09-30';},v=>{v.recent.recent.teams=['BUF','BUF'];},
    v=>{v.recent.daysBeforeForecast=null;},v=>{v.recent.observedDaysBeforeForecast=null;},
    v=>{v.recent.meanChange=1;},v=>{v.calendar.allTeams.observed=0;},
  ]) {const value=available();mutate(value);assert.equal(readForecastHistoryDisplay(value,expected),null);}
  const missingOnly=available();
  const missingWindow={rows:[rows[2]],wins:0,losses:0,ties:0,missing:1,decided:0,rate:null,mean:null};
  missingOnly.windows={'10':structuredClone(missingWindow),'20':structuredClone(missingWindow)};
  const missingSummary={games:1,observed:0,missing:1,mean:null,wins:0,decided:0,rate:null,
    newest:'2026-10-01',newestObserved:null,oldest:'2026-10-01',teams:['BUF']};
  missingOnly.recent={recent:structuredClone(missingSummary),previous:structuredClone(emptySummary),
    daysBeforeForecast:3,observedDaysBeforeForecast:null,meanChange:null};
  missingOnly.calendar.allTeams=structuredClone(missingSummary);
  missingOnly.calendar.capturedTeamSample=structuredClone(missingSummary);
  assert.ok(readForecastHistoryDisplay(missingOnly,expected),'Provided missing-stat rows have no invented mean or rate');
});

test('getters and sparse/exotic/hidden arrays cannot execute or become display output',()=>{
  let accessed=0;
  const getter=available();Object.defineProperty(getter,'parameters',{enumerable:true,get(){accessed++;return 'private';}});
  assert.equal(readForecastHistoryDisplay(getter,expected),null);
  const nested=available();Object.defineProperty(nested.recent,'recent',{enumerable:true,get(){accessed++;return summary;}});
  assert.equal(readForecastHistoryDisplay(nested,expected),null);
  for(const make of [
    ()=>new Array(1),
    ()=>{const value=['text'];Object.defineProperty(value,0,{enumerable:true,get(){accessed++;return 'text';}});return value;},
    ()=>{const value=['text'];Object.defineProperty(value,0,{enumerable:false,value:'text'});return value;},
    ()=>{const value=['text'];Object.defineProperty(value,'private',{value:'secret'});return value;},
    ()=>{const value=['text'];value.extra='secret';return value;},
    ()=>{const value=['text'];value[Symbol('private')]='secret';return value;},
  ]) {const value=available();value.context_labels[0].window=make();assert.equal(readForecastHistoryDisplay(value,expected),null);}
  const exotic=available();exotic.recent.previous=new Date();assert.equal(readForecastHistoryDisplay(exotic,expected),null);
  assert.equal(accessed,0);
});

test('row, label, string and collection limits are enforced without calculating replacement data',()=>{
  for(const mutate of [
    v=>{v.context_labels=Array(9).fill(v.context_labels[0]);},
    v=>{v.context_labels[0].window=Array(4).fill('text');},
    v=>{v.context_labels[0].window=['x'.repeat(1001)];},
    v=>{v.context_labels[0].recent='x'.repeat(3001);},
    v=>{v.card_summary='x'.repeat(2001);},v=>{v.producer_version='x'.repeat(65);},
    v=>{v.windows['10'].rows=Array(11).fill(rows[0]);},v=>{v.windows['20'].rows=Array(21).fill(rows[0]);},
    v=>{v.recent.recent.teams=Array(6).fill('BUF');},
  ]) {const value=available();mutate(value);assert.equal(readForecastHistoryDisplay(value,expected),null);}
});

test('the public history contract imports only declaration types and contains no private source dependency',()=>{
  const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
  const reviewed=new Set(['lib/forecastHistoryDisplay.ts','lib/types.ts']),visited=new Set(),queue=['lib/forecastHistoryDisplay.ts'];
  while(queue.length) {
    const name=queue.shift();if(visited.has(name)) continue;
    assert.ok(reviewed.has(name),'Unreviewed history display source: '+name);visited.add(name);
    const file=path.join(frontend,name),source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
    function inspect(node) {
      let specifier;
      if(ts.isImportDeclaration(node)||ts.isExportDeclaration(node)) specifier=node.moduleSpecifier;
      if(ts.isImportEqualsDeclaration(node)&&ts.isExternalModuleReference(node.moduleReference)) specifier=node.moduleReference.expression;
      if(ts.isCallExpression(node)&&(node.expression.kind===ts.SyntaxKind.ImportKeyword||ts.isIdentifier(node.expression)&&node.expression.text==='require')) {
        assert.equal(node.arguments.length,1,'Computed history display import');specifier=node.arguments[0];
      }
      if(ts.isImportTypeNode(node)) {assert.ok(ts.isLiteralTypeNode(node.argument));specifier=node.argument.literal;}
      if(specifier) {
        assert.ok(ts.isStringLiteralLike(specifier));const target=specifier.text;
        assert.ok(target.startsWith('.'),'Unexpected history display package import: '+target);
        const base=path.resolve(path.dirname(file),target),resolved=[base,base+'.ts'].find(value=>fs.existsSync(value));
        assert.ok(resolved,'Unresolved history display import');queue.push(path.relative(frontend,resolved).split(path.sep).join('/'));
      }
      ts.forEachChild(node,inspect);
    }
    inspect(source);
  }
  assert.deepEqual([...visited].sort(),[...reviewed].sort());
});
