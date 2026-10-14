import test from 'node:test';
import assert from 'node:assert/strict';
import {expectedProfit,parlayScenario} from '../lib/displayMath.ts';
import {forecastWindow,latestForecastWindow} from '../lib/forecastDisplayWindow.ts';

test('expected profit displays an existing return without creating one',()=>{
  assert.equal(expectedProfit(.12,100),12);
  assert.equal(expectedProfit(-.12,100),-12);
  assert.equal(expectedProfit(.12,0),0);
  for(const value of [null,undefined,'0.12',NaN,Infinity,-Infinity]) {
    assert.equal(expectedProfit(value,100),null);
  }
  for(const stake of [-1,NaN,Infinity,-Infinity]) assert.equal(expectedProfit(.12,stake),null);
});

test('parlay scenarios retain dependence bounds around the independence illustration',()=>{
  const result=parlayScenario([.6,.5],3);
  assert.equal(result.independent,.3);
  assert.ok(Math.abs(result.lower-.1)<1e-12);
  assert.equal(result.upper,.5);
  assert.ok(Math.abs(result.expectedReturn+.1)<1e-12);
  assert.deepEqual(parlayScenario([0,1],2),{independent:0,lower:0,upper:0,expectedReturn:-1});
  assert.deepEqual(parlayScenario([1,1],2),{independent:1,lower:1,upper:1,expectedReturn:1});
});

test('parlay display refuses unavailable probabilities and unsupported payouts',()=>{
  for(const probabilities of [[],[.5],[.5,NaN],[.5,Infinity],[-.1,.5],[1.1,.5]]) {
    assert.equal(parlayScenario(probabilities,3),null);
  }
  for(const payout of [0,1,-1,NaN,Infinity,-Infinity]) assert.equal(parlayScenario([.5,.5],payout),null);
});

test('forecast display moves to the archive exactly at game start',()=>{
  const now=Date.parse('2026-10-14T00:00:00Z');
  const upcoming={game_start_time:new Date(now+1).toISOString()};
  const started={game_start_time:new Date(now).toISOString()};
  assert.equal(forecastWindow(upcoming,now),'upcoming');
  assert.equal(forecastWindow(started,now),'archive');
  assert.equal(forecastWindow({game_start_time:new Date(now-1).toISOString()},now),'archive');
  assert.equal(forecastWindow({},now),'archive');
  assert.equal(forecastWindow({game_start_time:'invalid'},now),'archive');
  assert.equal(latestForecastWindow([started,upcoming],now),'upcoming');
  assert.equal(latestForecastWindow([started,{}],now),'archive');
  assert.equal(latestForecastWindow([],now),'archive');
});
