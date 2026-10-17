import test from 'node:test';
import assert from 'node:assert/strict';
import {engineDisplayReplyAsync,ENGINE_DISPLAY_PROTOCOL} from '../lib/engineTransport.ts';

const now=Date.now(),token='synthetic-engine-token-'.repeat(3),origin='https://engine.example.test';
const input=signal=>new Request('https://platform.example.test/api/signals?sport=nfl',{signal});
const envelope=()=>({protocol:ENGINE_DISPLAY_PROTOCOL,resource:'signals',generated_at:new Date(now-1000).toISOString(),
  expires_at:new Date(now+10000).toISOString(),revision:'a'.repeat(64),data:{label:'Recorded'}});
const options=patch=>({authorize:async()=>null,config:()=>({origin,token}),
  transport:async()=>Response.json(envelope()),now:()=>now,...patch});
async function unavailable(response) {
  assert.equal(response.status,503);
  assert.deepEqual(await response.json(),{error:'The evidence service is temporarily unavailable.'});
  for(const name of ['cache-control','cdn-cache-control','vercel-cdn-cache-control']) assert.equal(response.headers.get(name),'no-store');
}

test('async projection receives immutable metadata and the same upstream abort deadline',async()=>{
  let upstreamSignal,calls=0;
  const response=await engineDisplayReplyAsync(input(),'signals',async(data,context)=>{
    assert.equal(Object.isFrozen(context),true);assert.equal(context.signal,upstreamSignal);
    assert.deepEqual({...context,signal:undefined},{resource:'signals',method:'GET',
      request_url:input().url,generated_at:envelope().generated_at,expires_at:envelope().expires_at,
      revision:envelope().revision,signal:undefined});
    await Promise.resolve();return {label:data.label};
  },options({transport:async(url,init)=>{calls++;upstreamSignal=init.signal;return Response.json(envelope());}}));
  assert.equal(calls,1);assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{...envelope(),data:{label:'Recorded'}});
});

test('async projection rejects thenables, Promise subclasses and modified promises without invoking getters',async()=>{
  let executed=0;
  class OtherPromise extends Promise {}
  const ownThen=Promise.resolve({label:'bad'});
  Object.defineProperty(ownThen,'then',{get(){executed++;throw Error(token);}});
  const thenable=Object.defineProperty({},'then',{get(){executed++;throw Error(token);}});
  for(const project of [()=>thenable,()=>ownThen,()=>OtherPromise.resolve({label:'bad'}),()=>({label:'synchronous'})]) {
    await unavailable(await engineDisplayReplyAsync(input(),'signals',project,options()));
  }
  assert.equal(executed,0);
});

test('a malformed rejected native Promise is observed without executing its own then getter',async()=>{
  let getters=0;
  await unavailable(await engineDisplayReplyAsync(input(),'signals',()=>{
    const rejected=Promise.reject(Error(token));
    Object.defineProperty(rejected,'then',{get(){getters++;throw Error(token);}});
    return rejected;
  },options()));
  await new Promise(resolve=>setImmediate(resolve));assert.equal(getters,0);
});

test('caller abort returns while projection is pending and consumes its late rejection',async()=>{
  const controller=new AbortController();let rejectProjection,started;
  const begun=new Promise(resolve=>{started=resolve;});
  const pending=engineDisplayReplyAsync(input(controller.signal),'signals',()=>{
    started();return new Promise((resolve,reject)=>{rejectProjection=reject;});
  },options());
  await begun;controller.abort();await unavailable(await pending);
  rejectProjection(Error(token));await new Promise(resolve=>setImmediate(resolve));
});

test('one original 8000ms deadline covers pending projection without a renewed timer',async()=>{
  const original=AbortSignal.timeout,deadline=new AbortController();let timers=0,started;
  const begun=new Promise(resolve=>{started=resolve;});
  AbortSignal.timeout=milliseconds=>{assert.equal(milliseconds,8000);timers++;return deadline.signal;};
  try {
    const pending=engineDisplayReplyAsync(input(),'signals',()=>{started();return new Promise(()=>{});},options());
    await begun;deadline.abort();await unavailable(await pending);assert.equal(timers,1);
  } finally {AbortSignal.timeout=original;}
});

test('projection completion removes its abort listener and final expiry remains mandatory',async()=>{
  let clock=now,contextSignal,adds=0,removes=0;
  const response=await engineDisplayReplyAsync(input(),'signals',async(data,context)=>{
    const signal=context.signal;contextSignal=signal;
    const originalAdd=signal.addEventListener.bind(signal),originalRemove=signal.removeEventListener.bind(signal);
    // The body reader has already cleaned up; observe the projection listener removal.
    signal.addEventListener=(...args)=>{adds++;return originalAdd(...args);};
    signal.removeEventListener=(...args)=>{removes++;return originalRemove(...args);};
    await Promise.resolve();clock=now+20000;return {label:data.label};
  },options({now:()=>clock}));
  await unavailable(response);assert.ok(contextSignal);assert.equal(adds,0);assert.equal(removes,1);
});

test('post-auth admission rejects before config and never runs for a denied owner',async()=>{
  let admission=0,configuration=0,network=0;
  const guarded=options({admit:()=>{admission++;return 400;},config:()=>{configuration++;throw Error(token);},
    transport:async()=>{network++;throw Error(token);}});
  assert.equal((await engineDisplayReplyAsync(input(),'signals',async()=>({}),guarded)).status,400);
  assert.equal((await engineDisplayReplyAsync(input(),'signals',async()=>({}),{
    ...guarded,authorize:async()=>Response.json({error:'Owner authentication required.'},{status:401})})).status,401);
  assert.deepEqual([admission,configuration,network],[1,0,0]);
  await unavailable(await engineDisplayReplyAsync(input(),'signals',async()=>({}),{...guarded,admit:()=>undefined}));
  assert.equal(configuration,0);
});

test('async failures, unsafe output and credential reflection are sanitized',async()=>{
  for(const project of [async()=>{throw Error(token);},async()=>({label:token}),async()=>({probability:NaN}),
    async()=>({large:'x'.repeat(1024*1024)}),()=>{throw Error(token);},async()=>null]) {
    await unavailable(await engineDisplayReplyAsync(input(),'signals',project,options()));
  }
});
