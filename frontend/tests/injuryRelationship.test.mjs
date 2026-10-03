import test from 'node:test';
import assert from 'node:assert/strict';
import {publicSignals} from '../lib/signalMetrics.ts';
import {bestPicks,recentCandidateGroups} from '../lib/bestPicks.ts';
import {base} from './fixtures/qualifiedSignal.mjs';

const now=Date.parse('2026-10-08T17:00:00Z');
const captured=new Date(now).toISOString();

function fixture(sport,reportPatch={},coverage=true) {
  const root=sport==='nba' ? 'basketball/nba'
    : sport==='cfb' ? 'football/college-football' : 'football/nfl';
  const availability={...base.availability,captured_at:captured,team:'HME',player_id:'123',
    source_url:`https://site.api.espn.com/apis/site/v2/sports/${root}/injuries`,
    roster_source_url:`https://site.api.espn.com/apis/site/v2/sports/${root}/teams/12/roster`,
    ...(coverage ? {opponent_team:'AWY',opponent_injury_coverage:'observed'} : {})};
  const report={player:'Reported athlete',status:'Out',position:sport==='nba'?'SG':'CB',
    team:'AWY',relationship:'opponent',unit:'defense',reported_at:captured,
    source_url:availability.source_url,source_sha256:availability.source_sha256,...reportPatch};
  const [model,policy]=sport==='nba' ? ['nba-source-asof-v1','nba-source-asof-v1']
    : sport==='cfb' ? ['cfb-history-v1','cfb-explicit-receiving-v1']
    : ['nfl-history-v1','nfl-explicit-receiving-v1'];
  return {...base,sport,player_id:sport==='nfl'?'00-0000001':'123',
    model_version:`empirical-jeffreys-v4-${model}`,history_policy_version:policy,
    snapped_at:captured,captured_at:captured,history_observed_before:captured,
    forecast_cutoff:'2026-10-08',game_start_time:new Date(now+2*3600000).toISOString(),
    ...(sport==='nfl' ? {history_source_admission_policy:'nfl-core-history-source-admission-v1',
      history_source_verified:true} : {}),
    prop_type:sport==='nba'?'points':'pass_yds',
    market_type:sport==='nba'?'player_points':'player_pass_yds',
    availability:{...availability,teammates:[report]}};
}

for(const sport of ['nba','nfl','cfb']) {
  test(`${sport}: a structured position must support its claimed unit`,()=>{
    const positions=sport==='nba' ? ['WR','CB','Unknown'] : ['QB','WR','K','Unknown'];
    for(const position of positions) {
      const raw=fixture(sport,{position}),result=publicSignals([raw],now).signals[0];
      assert.equal(result.availability,undefined,position);
      assert.equal(result.gate_reason,'availability_unavailable');
      assert.equal(result.true_prob,raw.true_prob);
      assert.deepEqual(bestPicks([raw],now),[]);
      assert.deepEqual(recentCandidateGroups([raw],now),[]);
    }
  });

  test(`${sport}: contradictory injury relationships cannot qualify a pick`,()=>{
    for(const patch of [
      {team:'HME'},
      {team:'THR'},
      {relationship:'teammate'},
      {team:'HME',relationship:'teammate',unit:'defense'},
      {unit:'offense'},
    ]) {
      const raw=fixture(sport,patch),before=structuredClone(raw);
      const result=publicSignals([raw],now).signals[0];
      assert.equal(result.availability,undefined,JSON.stringify(patch));
      assert.equal(result.gated,true);assert.equal(result.gate_reason,'availability_unavailable');
      assert.equal(result.kelly_fraction,0);assert.equal(result.true_prob,raw.true_prob);
      assert.deepEqual(bestPicks([raw,result],now),[]);
      assert.deepEqual(recentCandidateGroups([raw,result],now),[]);
      assert.deepEqual(raw,before);
      assert.equal(publicSignals([result],now).signals[0].gated,true);
    }
  });

  test(`${sport}: coherent opponent and teammate reports retain their existing decisions`,()=>{
    for(const [patch,reason] of [
      [{},undefined],
      [{team:'HME',relationship:'teammate',unit:'offense',position:sport==='nba'?'SG':'WR',status:'Questionable'},undefined],
      [{team:'HME',relationship:'teammate',unit:'offense',position:sport==='nba'?'SG':'WR'},'teammate_availability_unmodeled'],
    ]) {
      const raw=fixture(sport,patch),result=publicSignals([raw],now).signals[0];
      assert.equal(result.availability.status,'observed');
      assert.deepEqual(result.availability.teammates,raw.availability.teammates);
      assert.equal(result.gated,reason!==undefined);assert.equal(result.gate_reason,reason);
      assert.equal(result.true_prob,raw.true_prob);
      assert.equal(bestPicks([raw],now).length,reason===undefined ? 1 : 0);
    }
  });

  test(`${sport}: legacy missing opponent coverage preserves uncertainty and rejects same-club opponents`,()=>{
    const original=fixture(sport,{},false),accepted=publicSignals([original],now).signals[0];
    assert.equal(accepted.availability.status,'observed');
    assert.equal(accepted.availability.opponent_injury_coverage,undefined);
    assert.equal(accepted.availability.opponent_team,undefined);
    assert.equal(accepted.true_prob,original.true_prob);
    const contradictory=publicSignals([fixture(sport,{team:'HME'},false)],now).signals[0];
    assert.equal(contradictory.availability,undefined);assert.equal(contradictory.gated,true);
    const legacy=fixture(sport,{},false);
    legacy.availability.teammates=[{player:'Legacy teammate',status:'Out',
      position:sport==='nba'?'SG':'WR',reported_at:captured}];
    const blocked=publicSignals([legacy],now).signals[0];
    assert.equal(blocked.availability.status,'observed');
    assert.equal(blocked.gate_reason,'teammate_availability_unmodeled');
  });
}
