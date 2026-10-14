import test from 'node:test';
import assert from 'node:assert/strict';
import {publicRecentParticipation,recentParticipationText} from '../lib/recentParticipation.ts';
import {publicSignals} from '../lib/signalMetrics.ts';
import {base} from './fixtures/qualifiedSignal.mjs';
const cutoff='2026-10-08',now=Date.parse('2026-10-08T17:00:00Z'),captured=new Date(now).toISOString();
const sample_window={cutoff,active:{oldest:'2025-09-01',newest:'2026-10-07'},
  absent:null,unknown:{oldest:'2026-09-30',newest:'2026-09-30'}};
const full={active:{games:3,mean:43.33,hit_rate:.6667},absent:{games:0,mean:null,hit_rate:null},unknown_games:1,sample_window};
const recent={version:'participation-recent-30d-v1',since:'2026-09-08',cutoff,
  active:{games:2,mean:15,hit_rate:.5},absent:{games:0,mean:null,hit_rate:null},unknown_games:1,
  sample_window:{cutoff,active:{oldest:'2026-09-08',newest:'2026-10-07'},absent:null,
    unknown:{oldest:'2026-09-30',newest:'2026-09-30'}}};

function signal(window=recent) {
  const source_url=base.availability.source_url;
  const report={player:'Receiver',status:'Questionable',position:'WR',team:'KC',relationship:'teammate',unit:'offense',
    reported_at:captured,source_url,source_sha256:base.availability.source_sha256};
  return {...base,forecast_cutoff:cutoff,player_id:'00-0000001',line:15.5,
    snapped_at:captured,captured_at:captured,history_observed_before:captured,
    game_start_time:new Date(now+2*3600000).toISOString(),
    model_version:'empirical-jeffreys-v4-nfl-history-v1',history_policy_version:'nfl-explicit-receiving-v1',
    history_source_admission_policy:'nfl-core-history-source-admission-v1',history_source_verified:true,
    availability:{...base.availability,captured_at:captured,teammates:[report],context_splits:[
    {...report,source:'nflverse_snap_counts',participation:'recorded unit snaps',evidence_version:'recorded-participation-v3',
      ...full,recent_window:window,source_rows:[{private:'proof'}],tenure_rows:[{private:'proof'}]}]}};
}

test('recent projection keeps exact groups and strips all private nested fields',()=>{
  const input={...recent,private:'alpha',source_rows:[{private:'proof'}],active:{...recent.active,private:'alpha'},
    sample_window:{...recent.sample_window,private:'alpha',active:{...recent.sample_window.active,private:'alpha'}}};
  const before=structuredClone(input);
  assert.deepEqual(publicRecentParticipation(input,full,cutoff),recent);
  assert.deepEqual(input,before);
});

test('old history cannot become recent through forged counts, dates or probabilities',()=>{
  for(const patch of [
    {version:'legacy'},{since:'2026-09-07'},{cutoff:'2026-10-09'},
    {active:{games:4,mean:15,hit_rate:.5}}, {unknown_games:2},
    {unknown_games:0}, {active:{games:0,mean:null,hit_rate:null}},
    {active:{games:2,mean:15,hit_rate:.7}}, {active:{games:2,mean:Infinity,hit_rate:.5}},
    {sample_window:{...recent.sample_window,active:{oldest:'2026-09-07',newest:'2026-10-07'}}},
    {sample_window:{...recent.sample_window,active:{oldest:'2026-09-08',newest:cutoff}}},
    {sample_window:{...recent.sample_window,active:null}},
    {sample_window:{...recent.sample_window,active:{oldest:'2026-09-08',newest:'2026-10-01'}}},
  ]) assert.equal(publicRecentParticipation({...recent,...patch},full,cutoff),undefined,JSON.stringify(patch));
  assert.equal(publicRecentParticipation(recent,{...full,sample_window:undefined},cutoff),undefined);
});

test('a whole cohort contained in 30 days must retain exact counts, averages and dates',()=>{
  const whole={...full,active:recent.active,sample_window:recent.sample_window};
  assert.deepEqual(publicRecentParticipation(recent,whole,cutoff),recent);
  for(const active of [{...recent.active,mean:999},{...recent.active,hit_rate:1},
    {games:1,mean:15,hit_rate:1}]) assert.equal(publicRecentParticipation({...recent,active},whole,cutoff),undefined);
});

test('empty recent cohorts are explicit and cannot invent an absence or fresh form',()=>{
  const older={...full,unknown_games:0,sample_window:{...sample_window,active:{oldest:'2025-09-01',newest:'2025-09-08'},unknown:null}};
  const empty={...recent,active:{games:0,mean:null,hit_rate:null},unknown_games:0,
    sample_window:{cutoff,active:null,absent:null,unknown:null}};
  assert.deepEqual(publicRecentParticipation(empty,older,cutoff),empty);
  assert.match(recentParticipationText({recent_window:empty}),/0 retrieved games/);
  assert.match(recentParticipationText({}),/not retained/);
});

test('consumer boundary preserves original forecasts and eligibility through repeated projections',()=>{
  const raw=signal({...recent,source_rows:[{private:'alpha'}]});const before=structuredClone(raw);
  const projected=publicSignals([raw],now).signals[0];
  assert.equal(projected.gated,false);
  const split=projected.availability.context_splits[0];
  assert.deepEqual(split.recent_window,recent);assert.deepEqual(split.active,full.active);
  assert.equal(projected.true_prob,raw.true_prob);
  assert.deepEqual(publicSignals([projected],now).signals[0].availability.context_splits,[split]);
  assert.equal(split.source_rows,undefined);assert.equal(split.tenure_rows,undefined);
  const baseline=publicSignals([signal(undefined)],now).signals[0];
  // Explicitly remove the optional field (the fixture's default is intentional).
  const old=signal();delete old.availability.context_splits[0].recent_window;
  const without=publicSignals([old],now).signals[0];
  assert.equal(projected.gated,without.gated);assert.equal(projected.gate_reason,without.gate_reason);
  assert.equal(projected.kelly_fraction,without.kelly_fraction);assert.equal(projected.true_prob,baseline.true_prob);
  assert.deepEqual(raw,before);
  const blocked=structuredClone(raw);
  blocked.availability.teammates[0].status='Out';blocked.availability.context_splits[0].status='Out';
  const withRecent=publicSignals([blocked],now).signals[0];
  delete blocked.availability.context_splits[0].recent_window;
  const oldBlocked=publicSignals([blocked],now).signals[0];
  assert.equal(withRecent.gate_reason,'teammate_availability_unmodeled');
  assert.equal(oldBlocked.gate_reason,withRecent.gate_reason);assert.equal(withRecent.true_prob,raw.true_prob);
});

test('damaged optional recent context withholds only that subset, preserving current reports',()=>{
  const original=publicSignals([signal()],now).signals[0];
  for(const window of [{...recent,since:'2025-01-01'},{...recent,unknown_games:100},null]) {
    const result=publicSignals([signal(window)],now).signals[0];
    assert.equal(result.availability.context_splits[0].recent_window,undefined);
    assert.deepEqual(result.availability.teammates,original.availability.teammates);
    assert.deepEqual(result.availability.context_splits[0].active,full.active);
    assert.equal(result.true_prob,original.true_prob);assert.equal(result.gate_reason,original.gate_reason);
  }
});

test('displayed dates describe the retrieved window and retain its coverage limit',()=>{
  const text=recentParticipationText({recent_window:recent});
  assert.match(text,/2026-09-08 to 2026-10-08 \(exclusive\)/);
  assert.match(text,/3 retrieved games; 1 with unknown participation/);
  assert.match(text,/not a complete schedule audit/);
});
