import test from 'node:test';
import assert from 'node:assert/strict';
import {marketCoverageText,propLinkageCoverageText,propQuoteCoverageText,sourceFailureText} from '../lib/marketCoverage.ts';

test('provider failures expose only approved operational reasons',()=>{
  assert.equal(sourceFailureText('access_denied'),'provider access denied');
  assert.equal(sourceFailureText('collection_cadence'),'waiting for scheduled sportsbook capture');
  assert.equal(sourceFailureText('rate_limited'),'provider rate limited');
  assert.equal(sourceFailureText('upstream_unavailable'),'provider temporarily unavailable');
  assert.equal(sourceFailureText('request_rejected'),'provider rejected the request');
  assert.equal(sourceFailureText('RuntimeError: secret URL'),null);
});

test('stage-specific Kalshi coverage forms two explicit partitions',()=>{
  assert.equal(marketCoverageText({discovered_games:15,attempted_games:15,observed_games:13,
    event_failed_games:2,market_failed_games:1,sample_complete_games:12,quoted_games:12,
    failed_games:3}),
  '13/15 event records observed, 2 event failures, 12 sampled games complete, 1 with partial market failures, 12 with quotes');
});

test('legacy captures keep their original non-partitioned wording',()=>{
  assert.equal(marketCoverageText({discovered_games:15,attempted_games:15,observed_games:13,
    quoted_games:12,failed_games:3}),
  '13/15 discovered games inspected, 12 with quotes, 3 with collection failures');
});

test('a complete sample still discloses a larger discovered game inventory',()=>{
  assert.equal(marketCoverageText({discovered_games:27,attempted_games:20,observed_games:20,
    event_failed_games:0,market_failed_games:0,sample_complete_games:20,quoted_games:20,failed_games:0}),
  '20/27 discovered games attempted · 20/20 event records observed, 0 event failures, 20 sampled games complete, 0 with partial market failures, 20 with quotes');
});

const linkage={prop_linked_markets:313,prop_linked_events:6,prop_open_markets:1802,prop_open_events:39};

test('prop linkage distinguishes sampled games from open inventory across discovered series',()=>{
  assert.equal(propLinkageCoverageText(linkage),
    '313 of 1802 observed open player props linked to sampled games across 6 of 39 prop events (open totals across discovered series)');
  const empty={prop_linked_markets:0,prop_linked_events:0,prop_open_markets:0,prop_open_events:0};
  assert.equal(propLinkageCoverageText({...empty,prop_discovery_complete:true}),
    '0 observed open player props across discovered series');
  assert.equal(propLinkageCoverageText({...empty,prop_discovery_complete:false}),
    '0 observed open player props across discovered series · prop discovery incomplete');
});

test('missing legacy denominators retain linked counts without inventing a total',()=>{
  for(const missing of ['prop_open_markets','prop_open_events']) {
    assert.equal(propLinkageCoverageText({...linkage,[missing]:undefined}),
      '313 player props linked to sampled games across 6 prop events');
  }
});

test('invalid or impossible prop linkage counts are hidden',()=>{
  for(const invalid of [{prop_linked_events:undefined},{prop_linked_markets:'313'},{prop_linked_markets:-1},
    {prop_linked_events:6.5},{prop_open_markets:null},{prop_open_markets:312},{prop_open_events:5},
    {prop_open_markets:313},{prop_open_events:undefined,prop_open_markets:0},
    {prop_open_markets:undefined,prop_open_events:Infinity}]) {
    assert.equal(propLinkageCoverageText({...linkage,...invalid}),null);
  }
});

test('prop quote coverage reports an exact market and ask-side partition',()=>{
  assert.equal(propQuoteCoverageText({prop_structured_quote_markets:3081,
    prop_yes_ask_quote_markets:3081,prop_no_ask_quote_markets:2822,
    prop_two_sided_quote_markets:2822,prop_one_sided_quote_markets:259,
    prop_unquoted_markets:0}),
  '3081 structured top-of-book markets · 2822 two-sided (91.6%) · 259 one-sided (3081 YES asks, 2822 NO asks) · 0 without displayed asks');
});

test('legacy prop captures keep a bounded fallback',()=>{
  assert.equal(propQuoteCoverageText({prop_structured_quote_markets:3,
    prop_two_sided_quote_markets:2}),
  '3 structured top-of-book markets (2 two-sided)');
});
