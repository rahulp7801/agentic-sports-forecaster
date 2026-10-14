import test from 'node:test';
import assert from 'node:assert/strict';
import { expectedProfit, signalMetrics } from '../lib/signalMetrics.ts';
import { POST, GET } from '../app/api/scan/route.ts';
import { GET as getPicks } from '../app/api/picks/route.ts';

test('public requests cannot start scans, including forged loopback Host headers', async () => {
  const response = await POST(new Request('http://localhost/api/scan', {method:'POST', headers:{host:'localhost'}}));
  assert.equal(response.status, 403);
  assert.equal((await GET(new Request('https://example.test/api/scan'))).status,401);
});

test('dollar profit uses expected return at actual payout, not probability edge', () => {
  // Pin the version era: this checks payout arithmetic, not today's model gate.
  const s = signalMetrics({sport:'nba',true_prob:.6,american_odds:100,direction:'over',
    model_version:'empirical-jeffreys-v4',sportsbook:'book'},Date.parse('2026-09-20T00:00:00Z'));
  assert.ok(Math.abs(expectedProfit(s.expected_return, 100)-20)<1e-10);
  assert.equal(expectedProfit(null, 100), null);
  assert.equal(expectedProfit(.2, -100), null);
});

test('invalid pick-board requests cannot be cached', async () => {
  const response=await getPicks(new Request('https://example.test/api/picks?sport=mlb'));
  assert.equal(response.status,401);
  assert.match(response.headers.get('cache-control'),/no-store/);
});
