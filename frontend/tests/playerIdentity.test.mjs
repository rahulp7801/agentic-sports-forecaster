import test from 'node:test';
import assert from 'node:assert/strict';
import {playerIdentity} from '../lib/playerIdentity.ts';

test('saved player identity separates same-name athletes and follows renamed athletes',()=>{
 const first={sport:'nfl',player:'Shared Name',player_id:'00-1'};
 const second={...first,player_id:'00-2'};
 const renamed={...first,player:'Updated Name'};
 assert.notEqual(playerIdentity(first),playerIdentity(second));
 assert.equal(playerIdentity(first),playerIdentity(renamed));
 assert.notEqual(playerIdentity(first),playerIdentity({...first,sport:'cfb'}));
});

test('older forecasts without an athlete ID use an explicit name fallback',()=>{
 assert.equal(playerIdentity({sport:'nba',player:'Shared Name'}),'nba:name:Shared Name');
 assert.equal(playerIdentity({sport:'nba',player:'Shared Name',player_id:''}),'nba:name:Shared Name');
});
