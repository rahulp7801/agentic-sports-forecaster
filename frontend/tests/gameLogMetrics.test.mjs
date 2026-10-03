import test from 'node:test';
import assert from 'node:assert/strict';
import {gameLog,gameLogAthletes,gameLogSelection,overFrequency} from '../lib/gameLogMetrics.ts';

test('NFL fields and unknown venue survive game-log parsing without invented zeros',()=>{
  const log=gameLog({player:'Example',pass_yds:'210',pass_tds:0,rec_yds:null,rush_yds:'',is_home:null},'nfl','1');
  assert.equal(log.pass_yds,210);assert.equal(log.pass_tds,0);
  assert.equal(log.rec_yds,undefined);assert.equal(log.rush_yds,undefined);
  assert.equal(log.home_away,undefined);
});
test('over frequency excludes missing stats and ties, and accepts a zero threshold',()=>{
  const logs=[21,20,19,null].map((points,i)=>gameLog({points},'nba',String(i)));
  assert.deepEqual(overFrequency(logs,'points',20),{wins:1,losses:1,pushes:1,missing:1,decided:2,rate:.5});
  assert.equal(overFrequency(logs,'points',0).rate,1);
  assert.equal(overFrequency(logs,'rebounds',20).rate,null);
  assert.equal(overFrequency(logs,'points',NaN),null);
});


test('CFB recorded results preserve explicit receiving zeros and unknown categories',()=>{
  const log=gameLog({player:'Recorded Receiver',date:'2026-09-26',team:'AAA',opponent:'BBB',rec_yds:0,receptions:0,rush_yds:null},'cfb','1');
  assert.equal(log.sport,'cfb');assert.equal(log.rec_yds,0);assert.equal(log.receptions,0);
  assert.equal(log.rush_yds,undefined);assert.equal(log.pass_tds,undefined);
  assert.deepEqual(overFrequency([log],'rec_yds',.5),{wins:0,losses:1,pushes:0,missing:0,decided:1,rate:0});
});


test('descriptive game-log rates keep distinct athlete IDs separate even for namesakes',()=>{
  const logs=[
    gameLog({player:'Shared Name',player_id:'123',team:'GSW',points:25},'nba','1'),
    gameLog({player:'Shared Name',player_id:'456',team:'BOS',points:10},'nba','2'),
    gameLog({player:'Renamed Player',player_id:'123',team:'BOS',points:30},'nba','3'),
    gameLog({player:'Unknown',team:'NYK',points:5},'nba','4'),
  ];
  const athletes=gameLogAthletes(logs);
  assert.deepEqual(athletes.map(a=>[a.playerId,a.logs.length]),[['123',2],['456',1]]);
  assert.equal(athletes[0].teams.size,2);
  assert.equal(overFrequency(athletes[0].logs,'points',20)?.rate,1);
  assert.equal(overFrequency(athletes[1].logs,'points',20)?.rate,0);
  assert.equal(logs[3].player_id,undefined);
  assert.equal(gameLogSelection(logs,'').selectedAthlete,undefined);
  assert.equal(gameLogSelection(logs,'').displayLogs.length,4);
  assert.deepEqual(gameLogSelection(logs,'123').displayLogs.map(log=>log.id),['1','3']);
  assert.equal(gameLogSelection([logs[0],logs[3]],'').selectedAthlete,undefined);
  assert.equal(gameLogSelection([logs[0]],'').selectedAthlete?.playerId,'123');
  assert.equal(gameLogSelection([logs[3]],'').selectedAthlete,undefined);
});
