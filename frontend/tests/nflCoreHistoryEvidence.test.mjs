import test from 'node:test';
import assert from 'node:assert/strict';
import {nflCoreHistoryPayloads} from '../lib/nflCoreHistoryEvidence.ts';

// Golden commitments produced by sportsbet.ingestion.provenance.stat_row_sha256.
const current='3e0b52071c10975bda88919cf9a7abebb21380b89069f445e0ba101ac638c24f';
const legacy='8f990f2b8a23224680a5a23c3b01b3284785379444152b7b9442435c420b0999';
const stat={player_id:'00-0036422',season:2024,week:1,team:'KC',
  passing_yards:240,rushing_yards:15,receiving_yards:0,receptions:3};

test('NFL core card history matches current and legacy Python row commitments',()=>{
  for(const digest of [current,legacy]) {
    const payload={player:'Player',pass_yds:240,rush_yds:15};
    assert.deepEqual(nflCoreHistoryPayloads([{payload,
      source_row:{...stat,source_record_sha256:digest}}]),[payload]);
  }
});

test('NFL core card history fails closed for stale or missing row commitments',()=>{
  const valid={payload:{pass_yds:240},source_row:{...stat,source_record_sha256:current}};
  for(const row of [
    {...valid,source_row:{...valid.source_row,passing_yards:400}},
    {...valid,source_row:{...valid.source_row,source_record_sha256:'a'.repeat(64)}},
    {payload:valid.payload},
    {...valid,source_row:{...valid.source_row,receptions:'3'}},
  ]) assert.throws(()=>nflCoreHistoryPayloads([valid,row]));
});
