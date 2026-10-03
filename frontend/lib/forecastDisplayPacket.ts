import {readForecastDisplayAuthority,type ForecastDisplayAuthority,type ForecastDisplayView} from './forecastDisplayAuthority.ts';
import {readSignalDisplaySnapshots} from './signalDisplay.ts';
import type {Sport} from './types';

export const FORECAST_RECORD_BINDING_PROTOCOL='linework-forecast-record-binding-v1';
export type ForecastDisplayRequest={sport:Sport|null;view:ForecastDisplayView;offset:number;limit:number;revision:string|null;player:string};
export type ForecastRecordBinding={protocol:typeof FORECAST_RECORD_BINDING_PROTOCOL;resource:'signals';
  request:ForecastDisplayRequest;payload_sha256:string};
export type ForecastDisplayPage=ReturnType<typeof readSignalDisplaySnapshots>&{
  search_player:string;total_count:number;research_window:string;display:ForecastDisplayAuthority;
  pagination:{offset:number;next_offset:number|null;revision:string;complete:boolean}};

const object=(value:unknown):value is Record<string,unknown>=>Boolean(value)&&typeof value==='object'&&!Array.isArray(value);
const count=(value:unknown,maximum:number):value is number=>Number.isSafeInteger(value)&&Number(value)>=0&&Number(value)<=maximum;
const digest=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);

/** Bounded canonical JSON; object key order is irrelevant, array order is retained. */
export function forecastDisplayJsonUsage(value:unknown):{json:string;bytes:number;nodes:number} {
  let nodes=0;
  const visit=(item:unknown,depth:number):string=>{
    if(++nodes>50_000||depth>32) throw Error('Invalid forecast JSON');
    if(item===null||typeof item==='boolean'||typeof item==='string') return JSON.stringify(item);
    if(typeof item==='number'&&Number.isFinite(item)) return JSON.stringify(item);
    if(!item||typeof item!=='object') throw Error('Invalid forecast JSON');
    const descriptors=Object.getOwnPropertyDescriptors(item);
    if(Reflect.ownKeys(item).some(key=>typeof key!=='string')
      ||Object.values(descriptors).some(entry=>!('value' in entry))) throw Error('Invalid forecast JSON');
    if(Array.isArray(item)) {
      if(Object.keys(descriptors).length!==item.length+1) throw Error('Invalid forecast JSON');
      return '['+Array.from({length:item.length},(_,index)=>{
        if(!descriptors[index]) throw Error('Invalid forecast JSON');
        return visit(descriptors[index].value,depth+1);
      }).join(',')+']';
    }
    if(Object.getPrototypeOf(item)!==Object.prototype&&Object.getPrototypeOf(item)!==null) throw Error('Invalid forecast JSON');
    return '{'+Object.keys(descriptors).sort().map(key=>JSON.stringify(key)+':'+visit(descriptors[key].value,depth+1)).join(',')+'}';
  };
  const result=visit(value,0);
  const bytes=new TextEncoder().encode(result).length;
  if(bytes>1024*1024) throw Error('Invalid forecast JSON');
  return {json:result,bytes,nodes};
}

export const canonicalForecastDisplayJson=(value:unknown)=>forecastDisplayJsonUsage(value).json;

export function validForecastDisplayRequest(value:unknown):value is ForecastDisplayRequest {
  if(!object(value)||Object.keys(value).length!==6
    ||(value.sport!==null&&!['nba','nfl','cfb'].includes(String(value.sport)))
    ||!['library','qualified','candidates'].includes(String(value.view))||!count(value.offset,999)
    ||!count(value.limit,100)||value.limit===0||(value.revision!==null&&!digest(value.revision))
    ||typeof value.player!=='string'||value.player!==value.player.trim()||value.player!==value.player.normalize('NFC')
    ||(value.player!==''&&!/^[\p{L}\p{M}.'\u2019 -]{1,80}$/u.test(value.player))
    ||(value.view!=='library'&&(value.offset!==0||value.revision!==null||value.player!==''))) return false;
  return true;
}

/** Integrity binding comes from the authenticated API, not an independent signature. */
export async function readForecastDisplayPacket(value:unknown,request:ForecastDisplayRequest):Promise<ForecastDisplayPage|null> {
  try {
    canonicalForecastDisplayJson(value);
    if(!validForecastDisplayRequest(request)||!object(value)||!object(value.binding)) return null;
    const binding=value.binding;
    if(Object.keys(binding).length!==4||binding.protocol!==FORECAST_RECORD_BINDING_PROTOCOL||binding.resource!=='signals'
      ||!validForecastDisplayRequest(binding.request)||!digest(binding.payload_sha256)
      ||canonicalForecastDisplayJson(binding.request)!==canonicalForecastDisplayJson(request)) return null;
    const payload=Object.fromEntries(Object.entries(value).filter(([key])=>key!=='binding'));
    const bytes=new TextEncoder().encode(canonicalForecastDisplayJson({protocol:binding.protocol,resource:binding.resource,
      request:binding.request,payload}));
    const actual=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes)),byte=>byte.toString(16).padStart(2,'0')).join('');
    if(actual!==binding.payload_sha256||value.search_player!==request.player||!Array.isArray(value.signals)
      ||value.signals.length>(request.view==='library' ? request.limit : 5000)||!Array.isArray(value.games)||value.games.length>100
      ||!count(value.invalid_signals,5000)||!count(value.total_count,50000)||!object(value.pagination)
      ||typeof value.research_window!=='string'||value.research_window.length>140||/[\u0000-\u001f]/.test(value.research_window)) return null;
    const pagination=value.pagination;
    if(pagination.offset!==request.offset||!digest(pagination.revision)||(request.revision!==null&&pagination.revision!==request.revision)
      ||typeof pagination.complete!=='boolean') return null;
    if(request.view!=='library') {
      if(pagination.next_offset!==null) return null;
    } else if(pagination.complete) {
      if(pagination.next_offset!==null||request.offset+request.limit<value.total_count) return null;
    } else if(!count(pagination.next_offset,1000)||pagination.next_offset<=request.offset
      ||pagination.next_offset>request.offset+request.limit||pagination.next_offset>value.total_count
      ||value.signals.length>pagination.next_offset-request.offset) return null;
    const projected=readSignalDisplaySnapshots([payload],request.sport ?? undefined);
    if(projected.invalid_signals!==0||projected.signals.length!==value.signals.length||projected.games.length!==value.games.length
      ||(request.player&&projected.signals.some(row=>!row.player.toLowerCase().includes(request.player.toLowerCase())))) return null;
    const display=readForecastDisplayAuthority(value.display,projected.signals,{revision:pagination.revision,view:request.view,
      complete:pagination.complete,invalid_signals:value.invalid_signals});
    if(!display) return null;
    return {...projected,search_player:request.player,invalid_signals:value.invalid_signals,total_count:value.total_count,
      research_window:value.research_window,display,pagination:{offset:request.offset,next_offset:pagination.next_offset as number|null,
        revision:pagination.revision,complete:pagination.complete}};
  } catch {return null;}
}
