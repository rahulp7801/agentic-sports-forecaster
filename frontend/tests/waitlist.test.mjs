import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptWaitlist,waitlistEmail,WAITLIST_BODY_LIMIT} from '../lib/waitlist.ts';
const base='https://example.test';
const request=(body,headers={},path='/api/waitlist')=>new Request(base+path,{method:'POST',headers:{origin:base,'Content-Type':'application/json',...headers},body:typeof body==='string'?body:JSON.stringify(body)});
const body={email:' Visitor@Example.COM ',website:'',consent:true};
test('waitlist normalizes email and gives the same private receipt for repeated consented signups',async()=>{
 const entries=new Set();const write=async email=>{entries.add(email);return true;};
 for(let i=0;i<2;i++) {const response=await acceptWaitlist(request(body),write);assert.equal(response.status,202);assert.deepEqual(await response.json(),{accepted:true});assert.equal(response.headers.get('Vercel-CDN-Cache-Control'),'no-store');}
 assert.deepEqual([...entries],['visitor@example.com']);
 for(const email of ['no-address','a@localhost','a@-example.com','a@ex..com','a\n@example.com','a'.repeat(65)+'@example.com'])assert.equal(waitlistEmail(email),null);
});
test('malformed, oversized, nonconsenting and foreign-origin requests never reach storage',async()=>{
 let calls=0;const write=async()=>{calls++;return true;};
 for(const candidate of [request('{'),request({...body,consent:false}),request({...body,email:'invalid'}),request({...body,token:'unexpected'}),request('x'.repeat(WAITLIST_BODY_LIMIT+1)),request(body,{'Content-Type':'text/plain'})]) assert.equal((await acceptWaitlist(candidate,write)).status,400);
 for(const headers of [{origin:'https://attacker.invalid'},{origin:''},{'sec-fetch-site':'cross-site'},{'sec-fetch-site':'same-site'}]) assert.equal((await acceptWaitlist(request(body,headers),write)).status,403);
 assert.equal((await acceptWaitlist(new Request(base+'/api/waitlist'),write)).status,405);
 assert.equal((await acceptWaitlist(request(body,{},'/api/waitlist?email=leak'),write)).status,400);
 assert.equal((await acceptWaitlist(request({...body,website:'bot-field'}),write)).status,202);assert.equal(calls,0);
});
test('database failure and durable rate limits never claim the email was saved',async()=>{
 assert.equal((await acceptWaitlist(request(body),async()=>{throw Error('secret-db-address');})).status,503);
 const response=await acceptWaitlist(request(body),async()=>false);assert.equal(response.status,429);assert.equal(response.headers.get('Retry-After'),'60');assert.ok(!(await response.text()).includes('Visitor'));
});
