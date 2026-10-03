import {publicRequest} from './publicRequest.ts';
import {NO_STORE_HEADERS} from './publicCache.ts';
export const WAITLIST_BODY_LIMIT=2048;
export function waitlistEmail(value:unknown):string|null {
  if(typeof value!=='string') return null;
  const email=value.trim().toLowerCase();
  if(email.length>254 || /[^\x21-\x7e]/.test(email)) return null;
  return /^[a-z0-9.!#$%&'*+\/=?^_`{|}~-]{1,64}@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$/.test(email) ? email : null;
}
async function boundedJson(request:Request) {
  if(!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) throw new Error('Invalid input');
  if(Number(request.headers.get('content-length') ?? 0)>WAITLIST_BODY_LIMIT) throw new Error('Invalid input');
  const reader=request.body?.getReader(); if(!reader) throw new Error('Invalid input');
  const chunks:Uint8Array[]=[],decoder=new TextDecoder('utf-8',{fatal:true});let bytes=0;
  try {while(true) {const {done,value}=await reader.read();if(done) break;
    bytes+=value.length;if(bytes>WAITLIST_BODY_LIMIT) {await reader.cancel();throw new Error('Invalid input');}chunks.push(value);
  }} finally {reader.releaseLock();}
  const body=new Uint8Array(bytes);let offset=0;for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.length;}
  return JSON.parse(decoder.decode(body));
}
/** No visitor can retrieve entries. Identical success for new and existing emails. */
export async function acceptWaitlist(request:Request,write:(email:string)=>Promise<boolean>) {
  const status=publicRequest(request);
  if(status) return Response.json({error:'Request rejected.'},{status,headers:NO_STORE_HEADERS});
  let email:string|null;
  try {
    const body=await boundedJson(request);
    if(!body || typeof body!=='object' || Array.isArray(body) || Object.keys(body).some(key=>!['email','website','consent'].includes(key)) || body.consent!==true || typeof body.website!=='string') throw new Error('Invalid input');
    email=waitlistEmail(body.email); if(!email) throw new Error('Invalid input');
    if(body.website) return Response.json({accepted:true},{status:202,headers:NO_STORE_HEADERS});
  } catch {return Response.json({error:'Enter a valid email and agree to the waitlist notice.'},{status:400,headers:NO_STORE_HEADERS});}
  try {
    if(!await write(email)) return Response.json({error:'Too many requests. Please try again later.'},{status:429,headers:{...NO_STORE_HEADERS,'Retry-After':'60'}});
    return Response.json({accepted:true},{status:202,headers:NO_STORE_HEADERS});
  } catch {return Response.json({error:'The waitlist is temporarily unavailable. Please try again later.'},{status:503,headers:NO_STORE_HEADERS});}
}
