import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {publicRunSelection, publicRunSelectionFromEnvironment} from '../public-run-selection.mjs';

const schedules = ['7 0,3,6,9,15,18,21 * * *', '7 12 * * *',
  '37 1,4,7,10,16,19,22 * * *', '37 13 * * *'];
const fixture = () => ({eventName: 'schedule', schedule: '7 12 * * *',
  operation: 'public_daily', sport: 'both', sha: 'a'.repeat(40),
  runId: '123456789', runAttempt: '1'});
const environment = () => ({GITHUB_EVENT_NAME: 'schedule', PUBLIC_RUN_SCHEDULE: '7 12 * * *',
  OPERATION: 'public_daily', SPORT: 'both', GITHUB_SHA: 'a'.repeat(40),
  GITHUB_RUN_ID: '123456789', GITHUB_RUN_ATTEMPT: '1'});
const fixedError = /^Error: Public run selection metadata is invalid$/;

test('receipt has only bounded run context, preserving identifiers as strings', () => {
  const input = {...fixture(), token: 'private-not-for-output', capture_timestamp: 'not-a-source-clock'};
  assert.deepEqual(publicRunSelection(input), {
    schema_version: 1, receipt_kind: 'public_run_selection', event_name: 'schedule',
    schedule: '7 12 * * *', selected_operation: 'public_daily', selected_sport: 'both',
    head_sha: 'a'.repeat(40), run_id: '123456789', run_attempt: '1',
  });
  assert.deepEqual(input, {...fixture(), token: 'private-not-for-output', capture_timestamp: 'not-a-source-clock'});
});

test('all existing cron, operation and sport values are recorded independently', () => {
  for (const schedule of schedules) {
    for (const operation of ['public_monitor', 'public_daily']) {
      for (const sport of ['both', 'nfl', 'nba', 'cfb']) {
        const receipt = publicRunSelection({...fixture(), schedule, operation, sport});
        assert.equal(receipt.schedule, schedule);
        assert.equal(receipt.selected_operation, operation);
        assert.equal(receipt.selected_sport, sport);
      }
    }
  }
});

test('an observed cron and operation mismatch is retained without inferring a correction', () => {
  const receipt = publicRunSelection({...fixture(), operation: 'public_monitor'});
  assert.equal(receipt.schedule, '7 12 * * *');
  assert.equal(receipt.selected_operation, 'public_monitor');
  assert.equal(Object.hasOwn(receipt, 'mode'), false);
});

test('manual dispatch has no cron and does not inherit a schedule default', () => {
  for (const schedule of [undefined, null, '']) {
    const receipt = publicRunSelection({...fixture(), eventName: 'workflow_dispatch', schedule,
      operation: 'public_monitor', sport: 'cfb'});
    assert.equal(receipt.event_name, 'workflow_dispatch');
    assert.equal(receipt.schedule, null);
    assert.equal(receipt.selected_operation, 'public_monitor');
    assert.equal(receipt.selected_sport, 'cfb');
  }
  assert.throws(() => publicRunSelection({...fixture(), eventName: 'workflow_dispatch'}), fixedError);
});

test('missing or unknown original schedule is rejected rather than inferred from a run clock', () => {
  for (const schedule of [undefined, null, '', '7 13 * * *', '7 12 * * *\n', 'x'.repeat(10000), {}]) {
    assert.throws(() => publicRunSelection({...fixture(), schedule}), fixedError);
  }
});

test('invalid fields and log injection cannot reach the receipt', () => {
  const faults = {
    eventName: [undefined, null, 'push', 'schedule\nprivate', {}],
    operation: [undefined, null, 'daily', 'scan', 'public_daily\nprivate', {}],
    sport: [undefined, null, 'all', 'NFL', 'nfl\nprivate', {}],
    sha: [undefined, null, 'a'.repeat(39), 'a'.repeat(41), 'A'.repeat(40), 'a'.repeat(40) + '\n', {}],
    runId: [undefined, null, 123456789, '0', '-1', '01', '1.5', '1e3', '1\n', '1\r', '1\nprivate', '1'.repeat(21), {}],
    runAttempt: [undefined, null, 1, '0', '-1', '01', '1.5', '1\n', '1\r', '1\nprivate', '1'.repeat(21), {}],
  };
  for (const [field, values] of Object.entries(faults)) {
    for (const value of values) {
      assert.throws(() => publicRunSelection({...fixture(), [field]: value}), fixedError,
        `${field} must be rejected`);
    }
  }
});

test('large decimal run identifiers retain their exact bytes without numeric conversion', () => {
  const receipt = publicRunSelection({...fixture(), runId: '99999999999999999999', runAttempt: '12345678901234567890'});
  assert.equal(receipt.run_id, '99999999999999999999');
  assert.equal(receipt.run_attempt, '12345678901234567890');
});

test('environment adapter reads only the seven allowlisted fields', () => {
  const allowed = environment();
  const observed = [];
  const receipt = publicRunSelectionFromEnvironment(new Proxy(allowed, {
    get(target, property) {
      observed.push(property);
      assert.ok(Object.hasOwn(allowed, property), 'unexpected environment read');
      return target[property];
    },
    ownKeys() { throw new Error('environment enumeration is forbidden'); },
  }));
  assert.deepEqual(new Set(observed), new Set(Object.keys(allowed)));
  assert.equal(observed.length, 7);
  assert.deepEqual(receipt, publicRunSelection(fixture()));
});

test('CLI emits one JSON line without reading the event file or unrelated environment values', () => {
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('../public-run-selection.mjs', import.meta.url))], {
    encoding: 'utf8', env: {...environment(), GITHUB_TOKEN: 'never-print-this-token',
      GITHUB_EVENT_PATH: 'missing-event-file-that-must-not-be-read', PRIVATE_PAYLOAD: 'never-print-this-payload'},
  });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, '');
  assert.equal(result.stdout.trim().split('\n').length, 1);
  assert.deepEqual(JSON.parse(result.stdout), publicRunSelection(fixture()));
  assert.equal(result.stdout.includes('never-print'), false);
});

test('CLI rejects invalid context with a fixed diagnostic and no echoed input', () => {
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('../public-run-selection.mjs', import.meta.url))], {
    encoding: 'utf8', env: {...environment(), PUBLIC_RUN_SCHEDULE: 'private-value\n::warning::injected'},
  });
  assert.equal(result.status, 1);
  assert.equal(result.stdout, '');
  assert.equal(result.stderr, 'Public run selection metadata is invalid\n');
});
