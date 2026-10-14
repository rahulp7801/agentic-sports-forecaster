import test from 'node:test';
import assert from 'node:assert/strict';
import {nflCoreHistoryPayloads} from '../lib/nflCoreHistoryEvidence.ts';
import {publicGameLogs} from '../lib/publicGameLogs.ts';

// Golden commitments produced by sportsbet.ingestion.provenance.stat_row_sha256.
const current='3e0b52071c10975bda88919cf9a7abebb21380b89069f445e0ba101ac638c24f';
const legacy='8f990f2b8a23224680a5a23c3b01b3284785379444152b7b9442435c420b0999';
const playerId='00-0036422';
const publicPayload={date:'2024-09-05',player:'Player',player_id:playerId,team:'KC',
  opponent:'BAL',is_home:true,pass_yds:240,rush_yds:15};
const stat={player_id:'00-0036422',season:2024,week:1,team:'KC',
  passing_yards:240,rushing_yards:15,receiving_yards:0,receptions:3};

test('NFL core card history matches current and legacy Python row commitments',()=>{
  for(const digest of [current,legacy]) {
    const payload={...publicPayload};
    assert.deepEqual(nflCoreHistoryPayloads([{payload,
      source_row:{...stat,source_record_sha256:digest}}],playerId),[payload]);
  }
});

test('NFL core card history fails closed for stale or missing row commitments',()=>{
  const valid={payload:{...publicPayload},source_row:{...stat,source_record_sha256:current}};
  for(const row of [
    {...valid,source_row:{...valid.source_row,passing_yards:400}},
    {...valid,source_row:{...valid.source_row,source_record_sha256:'a'.repeat(64)}},
    {payload:valid.payload},
    {...valid,source_row:{...valid.source_row,receptions:'3'}},
  ]) assert.throws(()=>nflCoreHistoryPayloads([valid,row],playerId));
});


test('a valid digest cannot authorize a different player, team or displayed core stat',()=>{
  const valid={payload:{...publicPayload},source_row:{...stat,source_record_sha256:current}};
  for(const changed of [
    {pass_yds:900},{rush_yds:99},{pass_yds:null},{rush_yds:undefined},
    {player_id:'00-0000001'},{team:'DEN'},
  ]) assert.throws(()=>nflCoreHistoryPayloads([{...valid,payload:{...valid.payload,...changed}}],playerId));
  assert.throws(()=>nflCoreHistoryPayloads([valid],'00-0000001'));
  assert.throws(()=>nflCoreHistoryPayloads([valid],''));
  assert.throws(()=>nflCoreHistoryPayloads([],''));
});

test('core history only exposes committed passing/rushing and public matchup fields',()=>{
  const payload={...publicPayload,pass_tds:9,rec_yds:99,receptions:10,
    source_sha256:'private-view-field',future_model_metadata:{score:.99}};
  const rows=[{payload,source_row:{...stat,source_record_sha256:current}}];
  assert.deepEqual(nflCoreHistoryPayloads(rows,playerId),[publicPayload]);
  assert.equal(rows[0].payload.pass_tds,9); // Do not mutate retained view data.
});


test('an explicitly unavailable core stat stays unavailable while a recorded zero remains zero',()=>{
  // Golden Python stat_row_sha256 commitment, not a locally mirrored hash.
  const source_row={...stat,passing_yards:null,rushing_yards:0,receiving_yards:null,receptions:null,
    source_record_sha256:'e852ae25d0936fdd6754f99ae85e193d7c1a886edc75ca7255448997af70eed0'};
  const payload={...publicPayload,pass_yds:null,rush_yds:0};
  const rows=publicGameLogs(nflCoreHistoryPayloads([{payload,source_row}],playerId),'nfl');
  assert.equal(Object.hasOwn(rows[0],'pass_yds'),false);
  assert.equal(rows[0].rush_yds,0);
  assert.equal(Object.hasOwn(rows[0],'source_row'),false);
});
