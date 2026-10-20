import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import {FORECAST_HISTORY_DISPLAY_PROTOCOL,readForecastHistoryDisplay} from '../lib/forecastHistoryDisplay.ts';

const require=createRequire(import.meta.url);
const file=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../components/PlayerHistoryDisplay.tsx');
const source=fs.readFileSync(file,'utf8');
const emitted=ts.transpileModule(source,{fileName:file,compilerOptions:{target:ts.ScriptTarget.ESNext,
  module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
const compiledModule={exports:{}};
new Function('require','module','exports',emitted)(specifier=>{
  if(specifier==='react'||specifier==='react/jsx-runtime') return require(specifier);
  if(specifier==='../lib/forecastHistoryDisplay') return {readForecastHistoryDisplay};
  if(specifier==='./ResearchViews.module.css') return {};
  throw Error('Unreviewed renderer dependency: '+specifier);
},compiledModule,compiledModule.exports);
const PlayerHistoryDisplay=compiledModule.exports.default;

const expected={revision:'b'.repeat(64),subject:{forecast_id:'synthetic-forecast',forecast_record_sha256:'a'.repeat(64),
  sport:'nfl',player:'Synthetic Athlete',player_id:'00-0000001',prop_type:'receptions',line:4.5,direction:'over'},
  scope:{captured_at:'2026-10-04T03:01:00Z',game_date_before:'2026-10-04',
    source_observed_before:'2026-10-04T03:00:10Z',source_cutoff_kind:'model_selection'}};
const rows=[{date:'2026-10-03',team:'BUF',opponent:'DET',stat:7,outcome:'Matched direction'},
  {date:'2026-10-02',team:'BUF',opponent:'DET',stat:4.5,outcome:'Tie'},
  {date:'2026-10-01',team:'BUF',opponent:'DET',stat:null,outcome:'Missing stat'}];
const emptySummary={games:0,observed:0,missing:0,mean:null,wins:0,decided:0,rate:null,
  newest:null,newestObserved:null,oldest:null,teams:[]};
function available() {
  const summary={games:3,observed:2,missing:1,mean:78.9,wins:1,decided:1,rate:.123,
    newest:'2026-10-03',newestObserved:'2026-10-03',oldest:'2026-10-01',teams:['BUF']};
  return structuredClone({protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:'supplied-display-v1',...expected,
    status:'available',source_coverage:'bounded_as_of_records',
    windows:{'10':{rows:rows.slice(0,1),wins:1,losses:0,ties:0,missing:0,decided:1,rate:.125,mean:123.4},
      '20':{rows,wins:1,losses:0,ties:1,missing:1,decided:1,rate:.625,mean:-12.3}},
    recent:{recent:summary,previous:emptySummary,daysBeforeForecast:1,observedDaysBeforeForecast:1,meanChange:null},
    calendar:{from:'2026-09-04',before:'2026-10-04',allTeams:summary,capturedTeam:null,
      capturedTeamSample:null,limitedToLatest20:true},card_summary:'Supplied descriptive card wording.',
    context_labels:[{player:'Synthetic Defender',team:'DET',relationship:'opponent',unit:'defense',
      window:['Recorded participation: 2026-09-01 to 2026-09-30.'],recent:'Supplied participation summary.'}]});
}
const render=(display,options={})=>renderToStaticMarkup(React.createElement(PlayerHistoryDisplay,
  {display,expected,...options}));

test('validated history renders supplied summaries and scope without recomputing from rows',()=>{
  const input=available(),before=structuredClone(input),html=render(input);
  assert.match(html,/Synthetic Athlete/);
  assert.match(html,/recorded model-selection cutoff \(2026-10-04T03:00:10Z\)/);
  assert.match(html,/<strong>-12\.3<\/strong>/,'Supplied mean must not become the raw-row mean');
  assert.match(html,/<strong>63%<\/strong>/,'Supplied rate must not be reconstructed from wins/decided');
  assert.match(html,/<strong>78\.9<\/strong>/);
  assert.match(html,/12% matched this direction/);
  assert.match(html,/Supplied descriptive card wording/);
  assert.match(html,/Recorded participation: 2026-09-01 to 2026-09-30/);
  assert.deepEqual(input,before);
});

test('both serializable initial windows select their supplied rows and accessible controls',()=>{
  const input=available(),ten=render(input,{initialWindow:10}),twenty=render(input);
  assert.match(ten,/<button type="button" aria-pressed="true">Last 10<\/button>/);
  assert.match(ten,/<button type="button" aria-pressed="false">Last 20<\/button>/);
  assert.match(ten,/<strong>123\.4<\/strong>/);assert.match(ten,/<strong>13%<\/strong>/);
  assert.doesNotMatch(ten,/<td>2026-10-02<\/td>|<td>2026-10-01<\/td>/);
  assert.match(twenty,/<button type="button" aria-pressed="true">Last 20<\/button>/);
  assert.match(twenty,/<td>2026-10-02<\/td>/);assert.match(twenty,/<td>2026-10-01<\/td>/);
  assert.match(twenty,/1 ties · 1 missing stats/);
});

test('an independently mismatched record or source binding withholds all supplied content',()=>{
  for(const mutate of [
    value=>{value.revision='c'.repeat(64);},value=>{value.subject.forecast_id='another-forecast';},
    value=>{value.subject.forecast_record_sha256='d'.repeat(64);},value=>{value.subject.player_id='00-0000002';},
    value=>{value.subject.line=5.5;},value=>{value.scope.captured_at='2026-10-04T03:02:00Z';},
    value=>{value.scope.source_observed_before='2026-10-04T03:00:20Z';},
    value=>{value.scope.game_date_before='2026-10-05';},value=>{value.scope.source_cutoff_kind='forecast_capture';},
  ]) {
    const binding=structuredClone(expected);mutate(binding);
    const html=render(available(),{expected:binding});
    assert.match(html,/Recorded player history is unavailable for this forecast/);
    assert.doesNotMatch(html,/Synthetic Athlete|Supplied descriptive|<table|Last 10|78\.9/);
  }
});

test('unknown unavailable reasons and malformed output use generic copy without stale summaries',()=>{
  const input={...available(),status:'unavailable',reason:'private upstream diagnostic that must not be rendered'};
  const html=render(input);
  assert.match(html,/Recorded player history is unavailable/);
  assert.doesNotMatch(html,/private upstream|Supplied descriptive|Synthetic Athlete|<table/);
  const malformed=available();malformed.windows['20'].mean=NaN;
  assert.match(render(malformed),/Recorded player history is unavailable/);
  assert.doesNotMatch(render(malformed),/NaN|Synthetic Athlete/);
});

test('a bound forecast-capture scope retains its supplied cutoff and distinct source label',()=>{
  const input=available();
  input.scope={...input.scope,source_observed_before:input.scope.captured_at,source_cutoff_kind:'forecast_capture'};
  const binding={...structuredClone(expected),scope:structuredClone(input.scope)};
  assert.equal(readForecastHistoryDisplay(input,binding)?.status,'available');
  const html=render(input,{expected:binding});
  assert.match(html,/forecast capture \(2026-10-04T03:01:00Z\)/);
  assert.doesNotMatch(html,/model-selection cutoff/);
  assert.match(html,/<strong>-12\.3<\/strong>/);
});

test('a valid unavailable DTO with a known reason retains only generic unavailable copy',()=>{
  const scope={captured_at:null,game_date_before:null,source_observed_before:null,source_cutoff_kind:'unavailable'};
  const input={...available(),scope,status:'unavailable',reason:'Original source cutoff is unavailable.'};
  const binding={...structuredClone(expected),scope:structuredClone(scope)};
  assert.equal(readForecastHistoryDisplay(input,binding)?.status,'unavailable');
  const html=render(input,{expected:binding});
  assert.match(html,/Recorded player history is unavailable for this forecast/);
  assert.doesNotMatch(html,/Original source cutoff|Synthetic Athlete|Supplied descriptive|78\.9|<table|Last 10/);
});

test('missing roster, ties, unknown games, source corrections and limited-history disclosures remain explicit',()=>{
  const html=render(available());
  for(const text of ['Roster team unavailable','did not retain a confirmed roster team','20-game display limit',
    'missing games are unknown','earlier versions of corrected rows may no longer be retained',
    'not a complete participation census','Ties and missing stats are excluded',
    'not betting returns or a new probability','no historical bookmaker prices are assumed'])
    assert.ok(html.includes(text),'Missing disclosure: '+text);
  const empty=available(),window={rows:[],wins:0,losses:0,ties:0,missing:0,decided:0,rate:null,mean:null};
  empty.windows={'10':structuredClone(window),'20':structuredClone(window)};
  empty.recent={recent:structuredClone(emptySummary),previous:structuredClone(emptySummary),
    daysBeforeForecast:null,observedDaysBeforeForecast:null,meanChange:null};
  empty.calendar.allTeams=structuredClone(emptySummary);empty.calendar.limitedToLatest20=false;
  const emptyHtml=render(empty);
  assert.match(emptyHtml,/No exact-player game records were available/);
  assert.match(emptyHtml,/No recorded games fall inside this window/);
  assert.match(emptyHtml,/This group does not establish current stat form/);
  assert.doesNotMatch(emptyHtml,/NaN|Infinity|<table/);
});

test('the prepared client has no data-fetch effects, raw log props or private producer imports',()=>{
  const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  assert.equal(tree.statements[0].expression.text,'use client');
  const imports=[];
  function inspect(node) {
    if(ts.isImportDeclaration(node)) imports.push(node.moduleSpecifier.text);
    if(ts.isCallExpression(node)&&ts.isIdentifier(node.expression))
      assert.ok(!['fetch','useEffect','useLayoutEffect','forecastHistory','recentForm','calendarForm'].includes(node.expression.text));
    ts.forEachChild(node,inspect);
  }
  inspect(tree);
  assert.deepEqual(imports,['react','../lib/forecastHistoryDisplay','./ResearchViews.module.css']);
  const props=tree.statements.find(node=>ts.isTypeAliasDeclaration(node)&&node.name.text==='Props');
  assert.deepEqual(props.type.members.map(member=>member.name.text),['display','expected','initialWindow']);
  assert.ok(props.type.members.every(member=>!ts.isFunctionTypeNode(member.type)));
});
