import test from 'node:test';
import assert from 'node:assert/strict';
import {publicRequest} from '../lib/publicRequest.ts';
import {gameLogRequest} from '../lib/publicGameLogs.ts';
const request=(path,method='GET',headers={})=>({url:'https://example.test'+path,method,headers:new Headers(headers)});
test('API boundary rejects mutation, ambiguous query values, excess input and foreign browser reads',()=>{
  for(const method of ['POST','PUT','PATCH','DELETE','TRACE','OPTIONS']) assert.equal(publicRequest(request('/api/signals',method)),405);
  assert.equal(publicRequest(request('/api/scan','POST')),403);
  for(const path of ['/api/signals?sport=nfl&sport=nba','/api/signals?cachebuster=1','/api/scans?x=1','/api/gamelogs?player='+ 'a'.repeat(129),'/api/gamelogs?player=a%00b']) assert.equal(publicRequest(request(path)),400);
  assert.equal(publicRequest(request('/api/gamelogs?player='+ 'a'.repeat(2100))),414);
  for(const site of ['cross-site','same-site','invalid']) {
    assert.equal(publicRequest(request('/api/signals','GET',{'sec-fetch-site':site})),403);
  }
  assert.equal(publicRequest(request('/api/signals','GET',{origin:'https://attacker.example'})),403);
  assert.equal(publicRequest(request('/api/signals','GET',{origin:'invalid'})),403);
  assert.equal(publicRequest(request('/api/unknown')),404);
});
test('ordinary API queries and a forged prefetch header still use the same boundary',()=>{
  for(const path of ['/api/signals?sport=nfl&view=qualified','/api/gamelogs?sport=nfl&player=Player&exact=1&before=2026-09-10&limit=40','/api/metrics?cohort=all&sport=nfl','/api/slate?sport=nba','/api/picks?sport=nfl','/api/scan']) assert.equal(publicRequest(request(path)),null);
  assert.equal(publicRequest(request('/api/signals?x=1','GET',{'next-router-prefetch':'1'})),400);
  assert.equal(publicRequest(request('/api/scans','GET',{'sec-fetch-site':'same-origin',origin:'https://example.test'})),null);
  assert.equal(publicRequest(request('/terminal?readiness=1')),null);
});

test('identity-bound history requests pass the outer boundary and inner validation together',()=>{
  for(const [sport,id] of [['nfl','00-0000001'],['nba','1630639'],['cfb','201']]) {
    const params=new URLSearchParams({sport,player_id:id,player:'Renamed Player',exact:'1',before:'2026-09-27',limit:'20'});
    const req=request('/api/gamelogs?'+params);
    assert.equal(publicRequest(req),null);
    assert.equal(gameLogRequest(new URL(req.url).searchParams).playerId,id);
    assert.equal(publicRequest(request('/api/gamelogs?'+params+'&player_id='+id)),400);
  }
  assert.equal(publicRequest(request('/api/gamelogs?player_id='+ '1'.repeat(129))),400);
  assert.equal(publicRequest(request('/api/signals?player_id=201')),400);
  assert.throws(()=>gameLogRequest(new URLSearchParams({sport:'nfl',player_id:"1' OR 1=1"})));
});


test('player search passes the read boundary while duplicate and control input is rejected',()=>{
  assert.equal(publicRequest(request('/api/signals?player=Aaron%20Rodgers&sport=nfl&view=library')),null);
  for(const path of ['/api/signals?player=A&player=B','/api/signals?player=Bad%00Name']) assert.equal(publicRequest(request(path)),400);
});
