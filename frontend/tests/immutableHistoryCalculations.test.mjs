import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {immutableHistoryCalculations} from '../lib/immutableHistoryCalculations.ts';
import {forecastHistory,recentForm,calendarForm} from '../lib/forecastHistory.ts';
import {pickCardFormSummary} from '../lib/pickCardForm.ts';

const props={nba:['points','rebounds','assists','threes','pra','steals','blocks'],
  nfl:['pass_yds','pass_tds','rush_yds','rec_yds','receptions'],cfb:['pass_yds','rush_yds','rec_yds','receptions']};
const dayBefore=(days)=>new Date(Date.parse('2026-10-14')-days*86400000).toISOString().slice(0,10);
function subject(sport='nfl',prop_type='receptions',patch={}) {
  const team=sport==='nba' ? 'BOS' : sport==='nfl' ? 'BUF' : 'BAMA';
  return {id:'a'.repeat(64),game_id:'synthetic-game',sport,player:'Synthetic Athlete',
    player_id:sport==='nfl' ? '00-0000001' : '123',prop_type,line:5,direction:'over',
    snapped_at:'2026-10-14T17:00:00Z',captured_at:'2026-10-14T17:01:00Z',
    game_start_time:'2026-10-14T21:00:00Z',model_version:'empirical-jeffreys-v4',forecast_cutoff:'2026-10-14',
    availability:{status:'observed',roster_confirmed:true,team,captured_at:'2026-10-14T17:00:00Z'},...patch};
}
function row(context,days,stat,patch={}) {
  return {date:dayBefore(days),player:context.player,player_id:context.player_id,
    team:context.availability?.team ?? 'BUF',opponent:context.sport==='nba' ? 'NYK' : 'DET',
    ...(context.prop_type==='pra' ? {points:stat,rebounds:0,assists:0} : {[context.prop_type]:stat}),...patch};
}
function original(logs,context) {
  return {windows:{'10':forecastHistory(logs,context,10),'20':forecastHistory(logs,context,20)},
    recent:recentForm(logs,context),calendar:calendarForm(logs,context),card_summary:pickCardFormSummary(logs,context)};
}
function parity(logs,context) {
  const before=structuredClone({logs,context});
  const result=immutableHistoryCalculations(logs,context);
  assert.deepEqual(result,original(logs,context));
  assert.deepEqual({logs,context},before);
  return result;
}

test('all supported sport, prop and direction outputs match the original private calculations',()=>{
  let cases=0;
  for(const [sport,markets] of Object.entries(props)) for(const prop of markets) for(const direction of ['over','under']) {
    const context=subject(sport,prop,{direction});
    const values=[7,5,null,1,0,10,5,undefined,3,8,6,1,5,2,7,4,9,undefined,0,5,2,1,9,6,3];
    const logs=values.map((value,index)=>row(context,index+1,value)).reverse();
    const result=parity(logs,context);
    assert.equal(result.windows['10'].rows.length,10);
    assert.equal(result.windows['20'].rows.length,20);
    assert.equal(result.recent.recent.games,5);assert.equal(result.recent.previous.games,5);
    assert.equal(result.calendar.limitedToLatest20,true);
    cases++;
  }
  assert.equal(cases,32);
});

test('signed football yards, missing values and ties keep the same descriptive rates and means',()=>{
  for(const sport of ['nfl','cfb']) for(const prop of ['pass_yds','rush_yds','rec_yds']) {
    const context=subject(sport,prop,{line:0,direction:'under'});
    const result=parity([-7,0,4,undefined,null].map((value,index)=>row(context,index+1,value)),context);
    assert.deepEqual(result.windows['20'].rows.map(item=>item.stat),[-7,0,4,null,null]);
    assert.equal(result.windows['20'].wins,1);assert.equal(result.windows['20'].losses,1);
    assert.equal(result.windows['20'].ties,1);assert.equal(result.windows['20'].missing,2);
    assert.equal(result.windows['20'].rate,.5);assert.equal(result.windows['20'].mean,-1);
  }
});

test('PRA still requires all three observed components and preserves zero instead of inventing missing stats',()=>{
  const context=subject('nba','pra',{line:0});
  const logs=[row(context,1,0,{points:0,rebounds:0,assists:0}),
    row(context,2,10,{assists:undefined}),row(context,3,8,{rebounds:null}),
    row(context,4,11,{points:6,rebounds:4,assists:1})];
  const result=parity(logs,context);
  assert.deepEqual(result.windows['20'].rows.map(item=>item.stat),[0,null,null,11]);
  assert.equal(result.windows['20'].ties,1);assert.equal(result.windows['20'].mean,5.5);
});

test('exact stable identity, retained calendar cutoff and sorted windows exclude other subjects and target games',()=>{
  const context=subject();
  const logs=[row(context,0,90),row(context,-1,90),row(context,3,2),
    row(context,1,8,{player:'Renamed Athlete'}),row(context,2,90,{player_id:'00-0000002'}),
    row(context,2,90,{player_id:undefined}),row(context,2,3)];
  const result=parity(logs,context);
  assert.deepEqual(result.windows['20'].rows.map(item=>item.stat),[8,3,2]);
  for(const sport of ['nba','nfl','cfb']) {
    const retained=subject(sport,props[sport][0]);
    for(const player_id of [undefined,'',sport==='nfl' ? '123' : '00-0000001']) {
      assert.throws(()=>immutableHistoryCalculations([],{...retained,player_id}),/Invalid forecast identity/);
    }
  }
});

test('empty, entirely missing and tied windows retain null metrics and observed-date distinctions',()=>{
  const context=subject();
  const empty=parity([],context);
  assert.equal(empty.windows['20'].mean,null);assert.equal(empty.windows['20'].rate,null);
  assert.equal(empty.recent.daysBeforeForecast,null);assert.equal(empty.calendar.capturedTeamSample.games,0);
  const missing=parity([row(context,1,undefined),row(context,2,null)],context);
  assert.equal(missing.recent.daysBeforeForecast,1);assert.equal(missing.recent.observedDaysBeforeForecast,null);
  assert.equal(missing.windows['20'].mean,null);assert.equal(missing.windows['20'].rate,null);
  assert.match(missing.card_summary,/this stat was unavailable/);
  const ties=parity([row(context,1,5),row(context,2,5)],context);
  assert.equal(ties.windows['20'].decided,0);assert.equal(ties.windows['20'].rate,null);
  assert.equal(ties.windows['20'].mean,5);
});

test('last-five windows stay disjoint and newer missing records never replace observed recency',()=>{
  const context=subject();
  const logs=[undefined,8,7,6,5,4,3,2,1,0].map((stat,index)=>row(context,index+1,stat));
  const result=parity(logs,context);
  assert.equal(result.recent.recent.mean,6.5);assert.equal(result.recent.previous.mean,2);
  assert.equal(result.recent.meanChange,4.5);assert.equal(result.recent.daysBeforeForecast,1);
  assert.equal(result.recent.observedDaysBeforeForecast,2);
  assert.equal(result.recent.recent.newest,dayBefore(1));assert.equal(result.recent.previous.newest,dayBefore(6));
  const older=parity([row(context,1,undefined),row(context,22,6)],context);
  assert.equal(older.recent.daysBeforeForecast,1);assert.equal(older.recent.observedDaysBeforeForecast,22);
  assert.match(older.card_summary,/Newer recorded game/);assert.match(older.card_summary,/does not establish current form/);
});

test('captured-team aliases match only within the retained sport and ignore later profile teams',()=>{
  const aliases={nfl:[['LAR','LA'],['WSH','WAS']],
    nba:[['GS','GSW'],['NO','NOP'],['NY','NYK'],['SA','SAS'],['UTAH','UTA'],['WSH','WAS']]};
  for(const [sport,pairs] of Object.entries(aliases)) for(const [left,right] of pairs) for(const [roster,stat] of [[left,right],[right,left]]) {
    const context=subject(sport,props[sport][0]);
    context.availability.team=roster;context.player_profile={team:'LAC'};
    const result=parity([row(context,1,7,{team:stat}),row(context,2,9,{team:'LAC'})],context);
    assert.equal(result.calendar.capturedTeam,roster);assert.equal(result.calendar.capturedTeamSample.games,1);
    assert.equal(result.calendar.capturedTeamSample.mean,7);
  }
  const cfb=subject('cfb','receptions');cfb.availability.team='GS';
  const result=parity([row(cfb,1,9,{team:'GSW'}),row(cfb,2,7,{team:'GS'})],cfb);
  assert.equal(result.calendar.capturedTeamSample.games,1);assert.equal(result.calendar.capturedTeamSample.mean,7);
});

test('30-day boundary, offseason, team changes and unavailable captured roster preserve card wording',()=>{
  const context=subject();
  const result=parity([row(context,1,6),row(context,2,8,{team:'ATL'}),
    row(context,30,4),row(context,31,20),row(context,150,40)],context);
  assert.equal(result.calendar.from,dayBefore(30));assert.equal(result.calendar.before,context.forecast_cutoff);
  assert.equal(result.calendar.allTeams.games,3);assert.equal(result.calendar.capturedTeamSample.games,2);
  assert.equal(result.calendar.capturedTeamSample.mean,5);
  for(const availability of [undefined,{status:'unavailable',roster_confirmed:false},
    {...context.availability,roster_confirmed:false}]) {
    const unavailable=parity([row(context,1,6)],{...context,availability});
    assert.equal(unavailable.calendar.capturedTeam,null);
    assert.equal(unavailable.card_summary,'Current-team form was not verified at forecast capture.');
  }
  assert.match(parity([row(context,31,9)],context).card_summary,/No BUF game appears/);
  assert.match(parity([row(context,1,6)],context).card_summary,/1 recorded stat in 1 game/);
  assert.match(parity([row(context,15,6)],context).card_summary,/does not establish current form/);
  assert.doesNotMatch(parity([row(context,14,6)],context).card_summary,/does not establish current form/);
});

test('retrieval limits and duplicate validation retain the original bounded latest-20 behavior',()=>{
  const context=subject();
  for(const count of [19,20,21,200]) {
    const logs=Array.from({length:count},(_,index)=>row(context,index+1,index%9)).reverse();
    const result=parity(logs,context);
    assert.equal(result.windows['20'].rows.length,Math.min(count,20));
    assert.equal(result.windows['10'].rows.length,10);
    assert.equal(result.calendar.limitedToLatest20,count>=20);
    assert.equal(result.card_summary.includes('Only the latest 20 records were checked.'),count>=20);
  }
  assert.throws(()=>immutableHistoryCalculations(Array.from({length:201},(_,index)=>row(context,index+1,1)),context),/Invalid game logs/);
  for(const logs of [[row(context,1,2),row(context,1,3)],
    [row(context,1,Infinity)],[row(context,1,-1)],[row(context,1,1,{date:'2026-02-31'})]]) {
    assert.throws(()=>immutableHistoryCalculations(logs,context));assert.throws(()=>original(logs,context));
  }
});

test('already resolved submillisecond chronology calculates without re-entering legacy admission',()=>{
  const context=subject('nfl','pass_yds',{line:249.5,
    snapped_at:'2026-10-14T17:00:00.000100+00:00',history_observed_before:'2026-10-14T17:00:00.000300+00:00',
    captured_at:'2026-10-14T17:00:00.000500+00:00',game_start_time:'2026-10-14T17:00:00.000900+00:00',
    model_version:'empirical-jeffreys-v4-nfl-history-v1',history_policy_version:'nfl-explicit-receiving-v1',
    availability:{status:'observed',roster_confirmed:true,team:'KC',captured_at:'2026-10-14T17:00:00.000250+00:00'}});
  // The immutable resolver has already retained source/generation/capture/receipt/start
  // ordering. Date.parse collapses the distinct capture and start to the same ms.
  assert.equal(Date.parse(context.captured_at),Date.parse(context.game_start_time));
  const logs=[row(context,1,260),row(context,2,240)];
  assert.throws(()=>forecastHistory(logs,context),/Forecast capture time unavailable/);
  const result=immutableHistoryCalculations(logs,context);
  const coarse={...context,game_start_time:'2026-10-14T21:00:00Z'};
  assert.deepEqual(result,original(logs,coarse));
  assert.equal(result.calendar.capturedTeam,'KC');assert.equal(result.calendar.capturedTeamSample.games,2);
  assert.equal(result.windows['20'].rate,.5);assert.equal(result.windows['20'].mean,250);
});

test('private extraction imports the resolved context only as a type and never invokes old admission or a source reader',()=>{
  const source=readFileSync(new URL('../lib/immutableHistoryCalculations.ts',import.meta.url),'utf8');
  const imports=[...source.matchAll(/^import[^\n]+/gm)].map(match=>match[0]);
  assert.deepEqual(imports,["import type {ImmutableForecastContext} from './immutableForecastHistory.ts';",
    "import {publicGameLogs,validPlayerId} from './publicGameLogs.ts';"]);
  assert.doesNotMatch(source,/historyObservedBefore|historyCutoff|capturedRosterTeam|\.\/forecastHistory|\.\/pickCardForm/);
  assert.doesNotMatch(source,/\bfetch\s*\(|\bEVSignal\b|resolveImmutableForecast\s*\(/);
});
