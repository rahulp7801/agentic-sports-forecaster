import {NO_STORE_HEADERS} from './publicCache.ts';
import {publicRequest} from './publicRequest.ts';

export const ENGINE_DISPLAY_PROTOCOL='linework-display-v1';
export const ENGINE_DISPLAY_RESOURCES=['benchmarks','gamelogs','games','kalshi-research','markets',
  'metrics','picks','polymarket','prop-screens','scans','signals','slate'] as const;
export type EngineDisplayResource=typeof ENGINE_DISPLAY_RESOURCES[number];
export type EngineReadConfig={origin:string|undefined;token:string|undefined};
export type EngineReadOptions={authorize:(request:Request)=>Promise<Response|null>;
  config:()=>EngineReadConfig;transport:typeof fetch;now?:()=>number};
export type EngineRequestContext=Readonly<{resource:EngineDisplayResource;request_url:string;method:string}>;
export type EngineProjectionContext=Readonly<EngineRequestContext&{
  generated_at:string;expires_at:string;revision:string;signal:AbortSignal}>;
export type EngineAsyncReadOptions=EngineReadOptions&{
  admit?:(context:EngineRequestContext)=>number|null};
export type DisplayEnvelope<T>={protocol:typeof ENGINE_DISPLAY_PROTOCOL;resource:EngineDisplayResource;
  generated_at:string;expires_at:string;revision:string;data:T};

const BODY_BYTES=1024*1024;
const TIMEOUT_MS=8000;
const unavailable=()=>Response.json({error:'The evidence service is temporarily unavailable.'},
  {status:503,headers:NO_STORE_HEADERS});

function configuredOrigin(config:EngineReadConfig) {
  if(typeof config.origin!=='string' || config.origin.length>300
    || typeof config.token!=='string' || !/^[\x21-\x7e]{32,512}$/.test(config.token)) throw new Error('Unavailable');
  const url=new URL(config.origin);
  if(url.protocol!=='https:' || url.username || url.password || url.pathname!=='/' || url.search || url.hash
    || url.port || !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(url.hostname)
    || !url.hostname.includes('.') || /^\d+(?:\.\d+){3}$/.test(url.hostname)
    || url.hostname.endsWith('.localhost') || /(?:^|\.)local$/.test(url.hostname)) throw new Error('Unavailable');
  return url.origin;
}

async function boundedJson(response:Response,signal:AbortSignal) {
  const length=response.headers.get('content-length');
  if(response.status!==200 || response.redirected
    || !/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')
    || (length!==null && (!/^(0|[1-9]\d*)$/.test(length) || Number(length)>BODY_BYTES))) {
    await response.body?.cancel().catch(()=>{});throw new Error('Unavailable');
  }
  const reader=response.body?.getReader();if(!reader) throw new Error('Unavailable');
  // The same deadline covers streamed reads, including a peer that stalls after headers.
  const cancel=()=>{void reader.cancel().catch(()=>{});};
  signal.addEventListener('abort',cancel,{once:true});
  const decoder=new TextDecoder('utf-8',{fatal:true});let text='',bytes=0;
  try {
    signal.throwIfAborted();
    while(true) {
      const {done,value}=await reader.read();signal.throwIfAborted();if(done) break;
      bytes+=value.byteLength;if(bytes>BODY_BYTES) {await reader.cancel();throw new Error('Unavailable');}
      text+=decoder.decode(value,{stream:true});
    }
    text+=decoder.decode();return JSON.parse(text) as unknown;
  } catch(error) {
    await reader.cancel().catch(()=>{});throw error;
  } finally {signal.removeEventListener('abort',cancel);reader.releaseLock();}
}

function timestamp(value:unknown):value is string {
  return typeof value==='string' && value.length<=64 && /([zZ]|[+-]\d\d:\d\d)$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function plainDisplay(value:unknown) {
  if(value===null || typeof value!=='object') return false;
  const queue:Array<{value:unknown;depth:number}>=[{value,depth:0}];let nodes=0;
  while(queue.length) {
    const item=queue.pop()!;if(++nodes>50000 || item.depth>32) return false;
    const current=item.value;
    if(current===null || typeof current==='string' || typeof current==='boolean') continue;
    if(typeof current==='number') {if(!Number.isFinite(current)) return false;continue;}
    if(typeof current!=='object') return false;
    const prototype=Object.getPrototypeOf(current);
    const array=Array.isArray(current);
    if(array ? prototype!==Array.prototype : prototype!==null && prototype!==Object.prototype) return false;
    if(array && (current.length>50000 || Object.keys(current).length!==current.length)) return false;
    const descriptors=Object.getOwnPropertyDescriptors(current);
    if(Object.getOwnPropertySymbols(current).length) return false;
    for(const [key,descriptor] of Object.entries(descriptors)) {
      if(array && key==='length') continue;
      if(array && (!/^(0|[1-9]\d*)$/.test(key) || Number(key)>=current.length)) return false;
      if(!descriptor.enumerable || !Object.hasOwn(descriptor,'value')) return false;
      queue.push({value:descriptor.value,depth:item.depth+1});
    }
  }
  return true;
}

/** Await only a native Promise, without executing a returned thenable or its getters. */
function boundedProjection(project:()=>unknown,signal:AbortSignal):Promise<{data:unknown}> {
  return new Promise((resolve,reject)=>{
    let settled=false;
    const finish=(result:{data:unknown}|null)=>{
      if(settled) return;settled=true;signal.removeEventListener('abort',cancel);
      if(result===null) reject(new Error('Unavailable'));else resolve(result);
    };
    const cancel=()=>finish(null);
    signal.addEventListener('abort',cancel,{once:true});
    try {
      signal.throwIfAborted();
      const pending=project();
      if(!pending || typeof pending!=='object' || Object.getPrototypeOf(pending)!==Promise.prototype
        || Object.hasOwn(pending,'constructor')) {finish(null);return;}
      // First-party projectors return ordinary native Promises. Observe malformed own-then
      // output before rejecting it, without invoking that property or dropping its rejection.
      const invalid=Object.getOwnPropertyNames(pending).length!==0;
      // Intrinsic then avoids reading an overridden .then; rejection is handled even after abort.
      Promise.prototype.then.call(pending,(data:unknown)=>finish({data}),()=>finish(null));
      if(invalid) finish(null);
      if(signal.aborted) cancel();
    } catch {finish(null);}
  });
}

async function displayReply(request:Request,resource:EngineDisplayResource,
  project:(data:unknown,context:EngineProjectionContext)=>unknown,
  options:EngineAsyncReadOptions,asynchronous:boolean):Promise<Response> {
  try {
    const context=Object.freeze({resource,request_url:request.url,method:request.method});
    const headers=new Headers(request.headers);
    // Authorization precedes configuration access and every upstream operation.
    const denied=await options.authorize(request);
    if(denied instanceof Response) return denied;
    if(denied!==null) return unavailable();
    if(!ENGINE_DISPLAY_RESOURCES.includes(resource)) return Response.json({error:'Unsupported display resource.'},
      {status:404,headers:NO_STORE_HEADERS});
    const input=new URL(context.request_url);
    if(input.pathname!==`/api/${resource}`) return Response.json({error:'Unsupported display request.'},
      {status:400,headers:NO_STORE_HEADERS});
    const rejected=publicRequest({url:context.request_url,method:context.method,headers});
    if(rejected) return Response.json({error:'Request rejected.'},{status:rejected,headers:NO_STORE_HEADERS});
    if(!['GET','HEAD'].includes(context.method)) return Response.json({error:'Request rejected.'},
      {status:405,headers:NO_STORE_HEADERS});
    if(options.admit) {
      const rejected=options.admit(context);
      if(rejected!==null) return Number.isInteger(rejected) && rejected>=400 && rejected<=499
        ? Response.json({error:'Request rejected.'},{status:rejected,headers:NO_STORE_HEADERS}) : unavailable();
    }
    const supplied=options.config(),config={origin:supplied.origin,token:supplied.token},origin=configuredOrigin(config);
    const url=new URL(`/v1/display/${resource}`,origin);url.search=input.search;
    const signal=AbortSignal.any([request.signal,AbortSignal.timeout(TIMEOUT_MS)]);
    signal.throwIfAborted();
    const upstream=await options.transport(url,{method:'GET',redirect:'error',cache:'no-store',credentials:'omit',
      headers:{Accept:'application/json',Authorization:`Bearer ${config.token}`},signal});
    const value=await boundedJson(upstream,signal);
    if(!value || typeof value!=='object' || Array.isArray(value)) return unavailable();
    const envelope=value as Record<string,unknown>,now=(options.now ?? Date.now)();
    if(!Number.isFinite(now) || Object.keys(envelope).length!==6
      || !['protocol','resource','generated_at','expires_at','revision','data'].every(key=>Object.hasOwn(envelope,key))
      || envelope.protocol!==ENGINE_DISPLAY_PROTOCOL || envelope.resource!==resource
      || !timestamp(envelope.generated_at) || !timestamp(envelope.expires_at)
      || Date.parse(envelope.generated_at)>now+60000 || Date.parse(envelope.expires_at)<=now
      || Date.parse(envelope.expires_at)<=Date.parse(envelope.generated_at)
      || typeof envelope.revision!=='string' || !/^[a-f0-9]{64}$/.test(envelope.revision)) return unavailable();
    const projectionContext=Object.freeze({...context,generated_at:envelope.generated_at,
      expires_at:envelope.expires_at,revision:envelope.revision,signal});
    const data=asynchronous
      ? (await boundedProjection(()=>project(envelope.data,projectionContext),signal)).data
      : project(envelope.data,projectionContext);
    if(data===null || data===undefined || !plainDisplay(data)) return unavailable();
    const reply:DisplayEnvelope<unknown>={protocol:ENGINE_DISPLAY_PROTOCOL,resource,
      generated_at:envelope.generated_at,expires_at:envelope.expires_at,revision:envelope.revision,data};
    const encoded=JSON.stringify(reply);
    if(new TextEncoder().encode(encoded).byteLength>BODY_BYTES) return unavailable();
    // A malformed producer or projection must not turn the service credential into display data.
    if(encoded.includes(JSON.stringify(config.token).slice(1,-1))) return unavailable();
    signal.throwIfAborted();
    const repliedAt=(options.now ?? Date.now)();
    if(!Number.isFinite(repliedAt) || Date.parse(envelope.expires_at)<=repliedAt) return unavailable();
    // Neither upstream headers/errors nor credentials are reflected to the caller.
    return new Response(context.method==='HEAD' ? null : encoded,
      {status:200,headers:{...NO_STORE_HEADERS,'Content-Type':'application/json; charset=utf-8'}});
  } catch {return unavailable();}
}

/** Synchronous projections remain synchronous: Promise output is rejected. */
export function engineDisplayReply<T>(request:Request,resource:EngineDisplayResource,
  project:(data:unknown)=>T|null,options:EngineReadOptions):Promise<Response> {
  return displayReply(request,resource,project,options,false);
}

/** One deadline covers the upstream read and an explicitly asynchronous public projection. */
export function engineDisplayReplyAsync<T>(request:Request,resource:EngineDisplayResource,
  project:(data:unknown,context:EngineProjectionContext)=>Promise<T|null>,options:EngineAsyncReadOptions):Promise<Response> {
  return displayReply(request,resource,project,options,true);
}
