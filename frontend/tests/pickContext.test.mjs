import test from 'node:test';
import assert from 'node:assert/strict';
import {capturedPlayerProfile,capturedRosterTeam,orderedInjuryReports,pickContext,pickContextCapture} from '../lib/pickContext.ts';
import {signalMetrics} from '../lib/signalMetrics.ts';
import {base} from './fixtures/qualifiedSignal.mjs';

const capturedBase={...base,captured_at:base.snapped_at};

test('acute teammate blockers remain visible before chronic and opponent reports',()=>{
  const reports=[
    {player:'Season injury',status:'Injured Reserve',relationship:'teammate'},
    {player:'Defender',status:'Out',relationship:'opponent'},
    {player:'Receiver',status:'Questionable',relationship:'teammate'},
    {player:'Quarterback',status:'Out',relationship:'teammate'},
    {player:'Running back',status:'Inactive',relationship:'teammate'},
  ].map(row=>({...row,position:'WR',reported_at:base.snapped_at}));
  const original=structuredClone(reports);
  const signal={...capturedBase,availability:{...base.availability,teammates:reports}};
  assert.match(pickContext(signal).reports,/Quarterback \(teammate, Out\), Running back \(teammate, Inactive\) and 3 more/);
  assert.deepEqual(orderedInjuryReports(reports).map(row=>row.player),
    ['Quarterback','Running back','Season injury','Defender','Receiver']);
  assert.deepEqual(reports,original);
  const metrics=signalMetrics(signal,Date.parse(base.snapped_at),true);
  assert.equal(metrics.gate_reason,'teammate_availability_unmodeled');
  assert.equal(metrics.true_prob,base.true_prob);
});

test('an opponent absence is labeled without becoming a teammate blocker',()=>{
  const signal={...capturedBase,availability:{...base.availability,teammates:[
    {player:'Defender',status:'Out',relationship:'opponent',position:'CB',reported_at:base.snapped_at},
  ]}};
  assert.match(pickContext(signal).reports,/Defender \(opponent, Out\)/);
  assert.equal(signalMetrics(signal,Date.parse(base.snapped_at),true).gate_reason,null);
});

test('a qualified suggestion shows verified roster and report context without a probability boost',()=>{
  const context=pickContext(capturedBase);
  assert.match(context.player,/roster confirmed/);
  assert.match(context.reports,/No relevant offensive teammate report/);
  assert.match(context.reports,/Opponent injury-report coverage was not retained/);
  assert.match(context.detail,/do not add a probability boost/);
});

test('opponent report coverage is explicit and cannot imply clearance when missing',()=>{
  const complete=pickContext({...capturedBase,availability:{...base.availability,
    opponent_team:'LV',opponent_injury_coverage:'observed'}});
  assert.match(complete.reports,/No relevant offensive teammate or opposing defender report/);
  const incomplete=pickContext({...capturedBase,availability:{...base.availability,
    opponent_team:'LV',opponent_injury_coverage:'unavailable'}});
  assert.match(incomplete.reports,/No relevant offensive teammate report/);
  assert.match(incomplete.reports,/Opponent injury-report coverage was unavailable/);
  assert.doesNotMatch(incomplete.reports,/No relevant offensive teammate or opposing defender report/);
});

test('reported absences and available historical comparisons are descriptive',()=>{
  const signal={...capturedBase,availability:{...base.availability,teammates:[
    {player:'Receiver',status:'Out',position:'WR',reported_at:base.snapped_at},
    {player:'Defender',status:'Questionable',position:'CB',reported_at:base.snapped_at},
  ],context_splits:[{player:'Receiver'}]},next_gen_stats:{sample_weeks:3}};
  const context=pickContext(signal);
  assert.match(context.reports,/Receiver \(Out\), Defender \(Questionable\)/);
  assert.match(context.detail,/1 historical participation comparison/);
  assert.match(context.detail,/3 prior tracking weeks/);
});

test('missing availability is not presented as a cleared context check',()=>{
  assert.match(pickContext({...base,availability:undefined}).player,/unavailable/);
});

test('archived roster evidence without forecast-time chronology is not called captured context',()=>{
  const missingSignal={...base,captured_at:undefined};
  const missing=pickContext(missingSignal);
  assert.match(missing.player,/Forecast-time.*unavailable/);
  assert.match(missing.reports,/could not be placed before/);
  assert.deepEqual(pickContextCapture(missingSignal,Date.parse(base.snapped_at)),{capturedAt:null,stale:true});
  const later={...capturedBase,availability:{...base.availability,
    captured_at:new Date(Date.parse(base.snapped_at)+1000).toISOString()}};
  assert.match(pickContext(later).player,/unavailable/);
  assert.deepEqual(pickContextCapture(later,Date.parse(base.snapped_at)+2000),{capturedAt:null,stale:true});
});

test('a refreshed player profile cannot relabel the team captured with a forecast',()=>{
  const identified={...capturedBase,availability:{...base.availability,player_id:'123'}};
  const profile={team:base.availability.team,player_id:'123',
    captured_at:capturedBase.captured_at,
    jersey:'11',position:'WR',image_url:'https://a.espncdn.com/captured.png'};
  assert.equal(capturedPlayerProfile({...identified,player_profile:profile}),profile);
  assert.equal(capturedPlayerProfile({...capturedBase,player_profile:profile}),undefined);
  assert.equal(capturedPlayerProfile({...identified,player_profile:{...profile,player_id:'999'}}),undefined);
  assert.equal(capturedPlayerProfile({...identified,player_profile:{...profile,
    captured_at:new Date(Date.parse(capturedBase.captured_at)+1000).toISOString()}}),undefined);
  const transferred={...identified,player_profile:{...profile,team:'NYJ'}};
  assert.equal(capturedRosterTeam(transferred),base.availability.team);
  assert.equal(capturedPlayerProfile(transferred),undefined);
  assert.equal(capturedRosterTeam({...transferred,captured_at:undefined}),null);
  assert.equal(capturedRosterTeam({...transferred,availability:{...base.availability,
    captured_at:new Date(Date.parse(capturedBase.captured_at)+1000).toISOString()}}),null);
});

test('injury context becomes stale one hour after its captured source',()=>{
  const signal={...base,captured_at:'2026-10-01T01:01:00Z',availability:{...base.availability,captured_at:'2026-10-01T01:00:00Z'}};
  assert.equal(pickContextCapture(signal,Date.parse('2026-10-01T02:00:00Z')).stale,false);
  assert.equal(pickContextCapture(signal,Date.parse('2026-10-01T02:00:01Z')).stale,true);
  assert.equal(pickContextCapture({...signal,availability:undefined},Date.parse('2026-10-01T01:01:00Z')).capturedAt,null);
  assert.equal(pickContextCapture({...signal,availability:{...signal.availability,captured_at:'2026-10-01T01:02:01Z'}},Date.parse('2026-10-01T01:01:00Z')).stale,true);
});
