import test from 'node:test';
import assert from 'node:assert/strict';
import {trackingSampleSummary} from '../lib/trackingSample.ts';
const base={cutoff_season:2026,cutoff_week:4,roster_team:'KC'};
test('tracking summary separates current season and current team without mutating evidence',()=>{
  const sample_periods=[{season:2025,week:18,team:'KC'},{season:2026,week:1,team:'NYJ'},
    {season:2026,week:3,team:'KC'},{season:2026,week:2,team:null}];
  const evidence={...base,sample_periods};const before=structuredClone(evidence);
  const result=trackingSampleSummary(evidence);
  assert.equal(result.range,'Recorded sample: 2025 Week 18 to 2026 Week 3.');
  assert.equal(result.composition,'3 of 4 weeks are from the 2026 season; 1 with KC that season.');
  assert.equal(result.teams,'Teams represented: KC, NYJ; 1 week with unknown team.');
  assert.equal(result.limitation,null);assert.deepEqual(evidence,before);
});
test('previous season and previous team do not establish current form',()=>{
  const previous=trackingSampleSummary({...base,sample_periods:[{season:2025,week:18,team:'KC'}]});
  assert.match(previous.limitation,/No 2026 tracking weeks/);
  const transferred=trackingSampleSummary({...base,sample_periods:[{season:2026,week:1,team:'NYJ'}]});
  assert.match(transferred.limitation,/No included week is from KC in the 2026 season/);
  assert.match(transferred.limitation,/3 NFL weeks before the target game/);
  assert.match(transferred.limitation,/byes or missing records/);
});
test('legacy tracking source timestamp cannot substitute for retained sample weeks',()=>{
  const result=trackingSampleSummary({...base,source_observed_at:'2026-09-29T00:00:00Z'});
  assert.match(result.range,/not retained/);assert.match(result.composition,/does not establish recent form/);
  assert.equal(result.teams,null);assert.equal(result.limitation,null);
});
