import assert from 'node:assert/strict';
import test from 'node:test';
import { gameLogRequest, publicGameLogs } from '../lib/publicGameLogs.ts';

test('public game logs retain real sport fields and strip unexpected view data',()=>{
  const nba=publicGameLogs([{date:'2026-04-12',player:'A.J. Lawson',team:'TOR',opponent:'BKN',
    is_home:true,points:10,minutes:10.6,pass_yds:999,source_sha256:'internal'}],'nba')[0];
  assert.deepEqual(nba,{date:'2026-04-12',player:'A.J. Lawson',team:'TOR',opponent:'BKN',
    is_home:true,points:10,minutes:10.6});
  const nfl=publicGameLogs([{date:'2026-09-10',player:'Runner',team:'LA',opponent:'SF',
    is_home:false,rush_yds:-1,receptions:0,points:99}],'nfl')[0];
  assert.equal(nfl.rush_yds,-1);assert.equal(nfl.receptions,0);assert.equal('points' in nfl,false);
  const cfb=publicGameLogs([{date:'2026-09-12',player:'Quarterback',team:'TEX',opponent:'OSU',
    is_home:true,pass_yds:281,pass_tds:4,points:99}],'cfb')[0];
  assert.equal(cfb.pass_yds,281);assert.equal('pass_tds' in cfb,false);assert.equal('points' in cfb,false);
});

test('public game logs reject malformed identity, dates, booleans, stats and oversized results',()=>{
  const valid={date:'2026-09-10',player:'Player',team:'LA',opponent:'SF',is_home:true,rush_yds:1};
  for(const changed of [{...valid,date:'yesterday'},{...valid,date:'2026-02-31'},{...valid,player:''},{...valid,is_home:'true'},
    {...valid,rush_yds:NaN},{...valid,receptions:-1},{...valid,rush_yds:10001}]) {
    assert.throws(()=>publicGameLogs([changed],'nfl'));
  }
  assert.throws(()=>publicGameLogs(Array(201).fill(valid),'nfl'));
});

test('college-football game-log requests retain exact player lookup',()=>{
  const request=gameLogRequest(new URLSearchParams({sport:'cfb',player:'A.J. Player',exact:'1',limit:'20'}));
  assert.deepEqual(request,{sport:'cfb',player:'A.J. Player',limit:20,exact:true,before:null,observedBefore:null});
});


test('stable IDs are sport-bound public fields and bounded query parameters',()=>{
  const base={date:'2026-09-20',player:'Player',team:'BUF',opponent:'DET'};
  for(const [sport,id] of [['nfl','00-0000001'],['nba','2544'],['cfb','4430807']]) {
    assert.equal(publicGameLogs([{...base,player_id:id,private_key:'hidden'}],sport)[0].player_id,id);
    const q=gameLogRequest(new URLSearchParams({sport,player_id:id,exact:'1'}));
    assert.equal(q.playerId,id);assert.equal(q.exact,true);
  }
  for(const id of ['',"00-0000001' OR 1=1",'2544',' 00-0000001','00-1'])
    assert.throws(()=>gameLogRequest(new URLSearchParams({sport:'nfl',player_id:id})));
  assert.throws(()=>publicGameLogs([{...base,player_id:'00-0000001'}],'cfb'));
  assert.throws(()=>publicGameLogs([{...base,player_id:2544}],'nba'));
});

test('NFL core history requests require exact identity and both pregame cutoffs',()=>{
  const valid={sport:'nfl',player_id:'00-0000001',player:'Player',exact:'1',
    before:'2026-10-04',observed_before:'2026-10-04T19:00:00Z',stat:'rush_yds'};
  assert.equal(gameLogRequest(new URLSearchParams(valid)).stat,'rush_yds');
  for(const patch of [{stat:'rec_yds'},{sport:'cfb',player_id:'123'},
    {exact:'0'},{player_id:''},{before:''},{observed_before:''}])
    assert.throws(()=>gameLogRequest(new URLSearchParams({...valid,...patch})));
});
