import test from 'node:test';
import assert from 'node:assert/strict';
import {createSnapshotCache} from '../lib/snapshotCache.ts';

for (const batch of [false, true]) {
  test(`${batch ? 'batch' : 'single'} snapshot expiry propagates failure and recovers`, async () => {
    let now = 0, calls = 0, offline = false, version = 1;
    const load = async () => {
      calls++;
      if (offline) throw new Error('offline');
      return {status: 'complete', version};
    };
    const cache = createSnapshotCache(load, async () => ({'scan:nfl': await load()}), () => now);
    const read = () => batch ? cache.snapshots(['scan:nfl']) : cache.snapshot('scan:nfl');
    const value = data => batch ? data['scan:nfl'] : data;
    assert.equal(value(await read()).version, 1);
    now = 59_999; offline = true;
    assert.equal(value(await read()).version, 1);
    assert.equal(calls, 1);
    now = 60_000;
    const failed = await Promise.allSettled([read(), read()]);
    assert.ok(failed.every(result => result.status === 'rejected' && result.reason.message === 'offline'));
    assert.equal(calls, 2);
    offline = false; version = 2;
    assert.equal(value(await read()).version, 2);
    assert.equal(calls, 3);
  });
}

test('expired readers wait for one fresh read rather than returning old state', async () => {
  let now = 0, resolve, calls = 0;
  const cache = createSnapshotCache(async () => {
    calls++;
    return calls === 1 ? {version: 1} : new Promise(done => {resolve = done;});
  }, async () => ({}), () => now);
  await cache.snapshot('scan:nfl'); now = 60_000;
  let completed = 0;
  const first = cache.snapshot('scan:nfl').then(value => {completed++; return value;});
  const second = cache.snapshot('scan:nfl').then(value => {completed++; return value;});
  await new Promise(done => setImmediate(done));
  assert.equal(completed, 0); assert.equal(calls, 2);
  resolve({version: 2});
  const [a, b] = await Promise.all([first, second]);
  a.version = 99;
  assert.equal(b.version, 2);
  assert.equal((await cache.snapshot('scan:nfl')).version, 2);
});

test('batch keys coalesce across ordering without mixing captures or changing caller keys', async () => {
  let manyCalls = 0, oneCalls = 0;
  const cache = createSnapshotCache(async key => {oneCalls++; return {key, capture: 1};}, async keys => {
    manyCalls++;
    return Object.fromEntries(keys.map(key => [key, {key, capture: 2}]));
  });
  await cache.snapshot('scan:nfl');
  const input = ['scan:nfl', 'scan:nba', 'scan:nfl'];
  const pending = cache.snapshots(input);
  input[0] = 'scan:cfb';
  const [a, b] = await Promise.all([pending, cache.snapshots(['scan:nba', 'scan:nfl'])]);
  assert.equal(oneCalls, 1); assert.equal(manyCalls, 1);
  assert.deepEqual(Object.keys(a), ['scan:nba', 'scan:nfl']);
  assert.equal(a['scan:nfl'].capture, 2);
  a['scan:nfl'].capture = 99;
  assert.equal(b['scan:nfl'].capture, 2);
  assert.deepEqual(await cache.snapshots([]), {});
  assert.equal(manyCalls, 1);
});

test('sport identity and delimiter-like keys cannot collide; missing snapshots can refresh', async () => {
  let now = 0, published = false, calls = 0;
  const cache = createSnapshotCache(async key => {calls++;return published ? {key} : null;},
    async keys => Object.fromEntries(keys.map(key => [key, {key}])), () => now);
  assert.equal(await cache.snapshot('scan:nfl'), null);
  assert.equal(await cache.snapshot('scan:nba'), null);
  assert.equal(calls, 2);
  published = true; now = 60_000;
  assert.deepEqual(await cache.snapshot('scan:nfl'), {key: 'scan:nfl'});
  assert.deepEqual(Object.keys(await cache.snapshots(['a,b', 'c'])), ['a,b', 'c']);
  assert.deepEqual(Object.keys(await cache.snapshots(['a', 'b,c'])), ['a', 'b,c']);
});
