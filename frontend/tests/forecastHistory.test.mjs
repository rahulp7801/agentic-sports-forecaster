import test from 'node:test';
import assert from 'node:assert/strict';
import {forecastHistory,historyCutoff,historyObservedBefore,recentForm,calendarForm} from '../lib/forecastHistory.ts';
import {gameLogRequest} from '../lib/publicGameLogs.ts';

const signal={player:'Player',sport:'nfl',forecast_cutoff:'2026-09-17',snapped_at:'2026-09-17T01:00:00Z',captured_at:'2026-09-17T01:01:00Z',game_start_time:'2026-09-18T00:00:00Z',prop_type:'receptions',line:4,direction:'under'};
const row=(date,receptions,player='Player')=>({date,player,team:'BUF',opponent:'DET',receptions});
test('history excludes target/future games and similar names, and keeps ties/missing out of rates',()=>{
  const result=forecastHistory([row('2026-09-18',9),row('2026-09-17',9),row('2026-09-16',8),row('2026-09-15',8,'Player Junior'),
    row('2026-09-15',0),row('2026-09-14',6),row('2026-09-13',4),row('2026-09-12',undefined)],signal);
  assert.equal(result.rows.length,4);assert.equal(result.wins,1);assert.equal(result.losses,1);
  assert.equal(result.ties,1);assert.equal(result.missing,1);assert.equal(result.rate,.5);
  assert.equal(result.mean,10/3);assert.equal(result.rows[0].stat,0);
  assert.equal(forecastHistory([row('2026-09-15',4)],signal).rate,null);
  assert.equal(forecastHistory([row('2026-09-15',undefined)],signal).mean,null);
});
test('history cutoff uses an overnight gap before UTC capture or earlier target and rejects unknown timing',()=>{
  assert.equal(historyCutoff(signal),'2026-09-16');
  assert.equal(historyCutoff({...signal,forecast_cutoff:'2026-09-14'}),'2026-09-14');
  assert.equal(historyCutoff({...signal,snapped_at:'2026-09-16T23:30:00-02:00'}),'2026-09-16');
  assert.equal(historyCutoff({...signal,snapped_at:'2026-09-16T00:00:00Z'}),'2026-09-15');
  assert.throws(()=>historyCutoff({...signal,snapped_at:'2026-09-16T20:00:00'}));
});
test('history observation cutoff requires a valid captured pregame forecast',()=>{
  assert.equal(historyObservedBefore(signal),'2026-09-17T01:01:00Z');
  for(const changed of [
    {captured_at:undefined},
    {captured_at:'2026-09-17T00:59:59Z'},
    {captured_at:'2026-09-18T00:00:00Z'},
    {captured_at:'2026-09-17T01:01:00'},
    {game_start_time:'invalid'},
    {game_start_time:undefined},
  ]) assert.throws(()=>historyObservedBefore({...signal,...changed}));
});

test('history windows sort before limiting, PRA requires all components, duplicate games fail closed',()=>{
  const result=forecastHistory([row('2026-09-13',3),row('2026-09-15',6)],signal,1);
  assert.equal(result.rows[0].date,'2026-09-15');assert.equal(result.rate,0);
  const nba={...signal,sport:'nba',prop_type:'pra',direction:'over',line:10};
  const base={date:'2026-09-15',player:'Player',team:'BOS',opponent:'NY'};
  assert.equal(forecastHistory([{...base,points:6,rebounds:4,assists:1}],nba).rows[0].stat,11);
  assert.equal(forecastHistory([{...base,points:6,rebounds:4}],nba).rows[0].stat,null);
  assert.throws(()=>forecastHistory([row('2026-09-15',3),row('2026-09-15',3)],signal));
  assert.throws(()=>forecastHistory([],{...signal,forecast_cutoff:'2026-02-31'}));
});
test('historical API query bounds exact names, limits and strict calendar cutoffs',()=>{
  const parse=value=>gameLogRequest(new URLSearchParams(value));
  assert.deepEqual(parse('sport=nfl&player=Player&exact=1&before=2026-09-17&limit=20'),
    {sport:'nfl',player:'Player',exact:true,before:'2026-09-17',observedBefore:null,limit:20});
  assert.equal(parse('limit=200').limit,200);assert.equal(parse('').before,null);
  assert.equal(parse('observed_before=2026-09-17T01%3A01%3A00Z').observedBefore,'2026-09-17T01:01:00Z');
  assert.equal(parse('sport=nba&player=Luka%20Don%C4%8Di%C4%87').player,'Luka Dončić');
  for(const value of ['observed_before=2026-02-31T01:01:00Z','observed_before=2026-09-17T01:01:00','observed_before=2026-09-17T25:01:00Z','observed_before=0000-09-17T01:01:00Z','observed_before=2026-09-17T01:01:00%2B14:01','observed_before=','before=2026-02-31','before=0000-01-01','before=2026-09-17T00:00Z','before=','exact=1','exact=2','limit=Infinity','limit=0','limit=201','limit=999999','sport=mlb','player=A%00B','player=%25','player=%20Player','player=%F0%9F%8F%88']) assert.throws(()=>parse(value));
});


test('stable athlete identity wins over display names without mixing same-name players',()=>{
  const identified={...signal,player_id:'00-0000001'};
  const rows=[{...row('2026-09-15',3),player_id:'00-0000002'},
    {...row('2026-09-15',1,'Renamed Player'),player_id:'00-0000001'}];
  assert.deepEqual(forecastHistory(rows,identified).rows.map(r=>r.stat),[1]);
  assert.equal(forecastHistory([row('2026-09-15',3)],identified).rows.length,0);
  assert.throws(()=>forecastHistory(rows,signal));
  assert.throws(()=>forecastHistory(rows,{...signal,player_id:'invalid'}));
});

test('recent form keeps disjoint windows, missing rows, dates and team changes',()=>{
  const rows=[9,8,7,undefined,5,4,3,2,1,0].map((stat,index)=>({
    ...row(`2026-09-${String(15-index).padStart(2,'0')}`,stat),team:index===2?'ATL':'BUF'}));
  const before=structuredClone(rows);const form=recentForm(rows,signal);
  assert.equal(form.recent.games,5);assert.equal(form.recent.observed,4);assert.equal(form.recent.missing,1);
  assert.equal(form.recent.mean,7.25);assert.equal(form.previous.mean,2);
  assert.equal(form.meanChange,5.25);assert.equal(form.previous.decided,4);
  assert.equal(form.previous.rate,1);assert.equal(form.daysBeforeForecast,2);
  assert.deepEqual(form.recent.teams,['BUF','ATL']);assert.deepEqual(rows,before);
});

test('small and offseason history do not imply a full or current sample',()=>{
  const form=recentForm([row('2026-05-01',undefined)],signal);
  assert.equal(form.recent.games,1);assert.equal(form.recent.mean,null);
  assert.equal(form.previous.games,0);assert.equal(form.meanChange,null);
  assert.ok(form.daysBeforeForecast>30);
  assert.equal(recentForm([],signal).daysBeforeForecast,null);
});


test('calendar form excludes offseason games and separates captured team from later profile',()=>{
  const s={...signal,availability:{status:'observed',roster_confirmed:true,team:'BUF'},player_profile:{team:'ATL'}};
  const logs=[row('2026-09-15',0),{...row('2026-09-14',8),team:'ATL'},row('2026-08-18',4),row('2026-08-17',20),row('2026-05-01',40)];
  const before=structuredClone(logs);const form=calendarForm(logs,s);
  assert.equal(form.from,'2026-08-18');assert.equal(form.before,'2026-09-16');
  assert.equal(form.allTeams.games,3);assert.equal(form.allTeams.mean,4);
  assert.equal(form.capturedTeam,'BUF');assert.equal(form.capturedTeamSample.games,2);
  assert.equal(form.capturedTeamSample.mean,2);assert.equal(form.capturedTeamSample.decided,1);
  assert.equal(form.capturedTeamSample.wins,1);assert.deepEqual(logs,before);
});

test('unknown roster and empty current team history stay distinct from zero stats',()=>{
  const logs=[row('2026-09-15',undefined)];
  assert.equal(calendarForm(logs,signal).capturedTeamSample,null);
  const s={...signal,availability:{status:'observed',roster_confirmed:true,team:'ATL'}};
  assert.equal(calendarForm(logs,s).capturedTeamSample.games,0);
  assert.equal(calendarForm(logs,s).allTeams.missing,1);
  assert.equal(calendarForm(logs,s).allTeams.mean,null);
  assert.equal(calendarForm([row('2026-05-01',8)],s).allTeams.games,0);
  assert.equal(calendarForm(logs,{...s,availability:{...s.availability,roster_confirmed:false}}).capturedTeamSample,null);
});

test('calendar windows preserve identity and overnight cutoff and expose the display bound',()=>{
  const logs=Array.from({length:22},(_,i)=>row(new Date(Date.parse('2026-09-15')-i*86400000).toISOString().slice(0,10),i));
  assert.equal(calendarForm(logs,signal).limitedToLatest20,true);
  assert.equal(calendarForm(logs,signal).allTeams.games,20);
  assert.equal(calendarForm([row('2026-09-16',99),row('2026-09-15',1)],signal).allTeams.mean,1);
  assert.equal(calendarForm([{...row('2026-09-15',10),player_id:'00-0000002'}],{...signal,player_id:'00-0000001'}).allTeams.games,0);
  assert.throws(()=>calendarForm([],{...signal,snapped_at:'invalid'}));
});
