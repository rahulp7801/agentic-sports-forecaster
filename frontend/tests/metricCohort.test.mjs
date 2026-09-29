import test from 'node:test';
import assert from 'node:assert/strict';

import { metricCohort, metricLedgerArgs, metricSnapshotKey, metricSport } from '../lib/metricCohort.ts';

test('metric cohort defaults to all and accepts only published cohorts', () => {
  assert.equal(metricCohort('https://example.test/api/metrics'), 'all');
  assert.equal(metricCohort('https://example.test/api/metrics?cohort=recommendations'), 'recommendations');
  assert.equal(metricCohort('https://example.test/api/metrics?cohort=combined'), null);
});

test('metric sport defaults to all and rejects unsupported leagues', () => {
  assert.equal(metricSport('https://example.test/api/metrics'), 'all');
  assert.equal(metricSport('https://example.test/api/metrics?sport=nfl'), 'nfl');
  assert.equal(metricSport('https://example.test/api/metrics?sport=mlb'), null);
});

test('metric cohort selects the matching hosted snapshot and local ledger mode', () => {
  assert.equal(metricSnapshotKey('all'), 'metrics:all');
  assert.equal(metricSnapshotKey('recommendations'), 'metrics:recommendations');
  assert.equal(metricSnapshotKey('all','nfl'), 'metrics:all:nfl');
  assert.deepEqual(metricLedgerArgs('all'), ['-m', 'sportsbet.ledger']);
  assert.deepEqual(metricLedgerArgs('recommendations'), [
    '-m', 'sportsbet.ledger', '--recommendations-only'
  ]);
  assert.deepEqual(metricLedgerArgs('recommendations','nba'), [
    '-m', 'sportsbet.ledger', '--recommendations-only', '--sport', 'nba'
  ]);
});


test('CFB metrics select their own published and local model cohort',()=>{
  assert.equal(metricSport('https://example.test/api/metrics?sport=cfb'),'cfb');
  for(const cohort of ['all','recommendations']) {
    assert.equal(metricSnapshotKey(cohort,'cfb'),`metrics:${cohort}:cfb`);
    assert.deepEqual(metricLedgerArgs(cohort,'cfb'),['-m','sportsbet.ledger',
      ...(cohort==='recommendations' ? ['--recommendations-only'] : []),
      '--sport','cfb','--model-version','empirical-jeffreys-v4-cfb-history-v1']);
  }
});


test('NFL metrics select the corrected-history cohort',()=>{
  assert.deepEqual(metricLedgerArgs('all','nfl'),['-m','sportsbet.ledger','--sport','nfl',
    '--model-version','empirical-jeffreys-v4-nfl-history-v1']);
});
