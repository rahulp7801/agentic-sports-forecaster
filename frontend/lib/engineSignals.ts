import {engineDisplayReplyAsync,type EngineAsyncReadOptions,type EngineProjectionContext,
  type EngineRequestContext} from './engineTransport.ts';
import {canonicalForecastDisplayJson,readForecastDisplayPacket,validForecastDisplayRequest,
  type ForecastDisplayRequest} from './forecastDisplayPacket.ts';

/** Public request grammar, kept in parity with the current signals route by offline tests. */
export function engineSignalsRequest(context:Pick<EngineRequestContext,'resource'|'request_url'>):Readonly<ForecastDisplayRequest>|null {
  try {
    if(typeof context.request_url!=='string') return null;
    const url=new URL(context.request_url);
    if(context.resource!=='signals' || url.pathname!=='/api/signals' || url.hash || context.request_url.length>2048) return null;
    const seen=new Set<string>();
    for(const [key,value] of url.searchParams) {
      if(!['sport','view','offset','limit','revision','player'].includes(key) || seen.has(key)
        || value.length>128 || /[\u0000-\u001f]/.test(value)) return null;
      seen.add(key);
    }
    const offset=url.searchParams.get('offset') ?? '0',limit=url.searchParams.get('limit') ?? '100';
    if(!/^(0|[1-9][0-9]{0,3})$/.test(offset) || !/^[1-9][0-9]{0,2}$/.test(limit)) return null;
    const request={sport:url.searchParams.get('sport'),view:url.searchParams.get('view') ?? 'library',
      offset:Number(offset),limit:Number(limit),revision:url.searchParams.get('revision'),player:url.searchParams.get('player') ?? ''};
    return validForecastDisplayRequest(request) ? Object.freeze(request) : null;
  } catch {return null;}
}

/** Decode a copied output packet; outer metadata never supplies missing packet authority. */
export async function projectEngineSignals(data:unknown,context:EngineProjectionContext) {
  try {
    const request=engineSignalsRequest(context),revision=context.revision;
    if(!request || typeof revision!=='string' || !/^[a-f0-9]{64}$/.test(revision)
      || (request.revision!==null && request.revision!==revision)) return null;
    // Copy before WebCrypto awaits: neither the packet nor its request can change during validation.
    const packet=JSON.parse(canonicalForecastDisplayJson(data)) as unknown;
    const page=await readForecastDisplayPacket(packet,request);
    if(!page || page.pagination.revision!==revision || page.display.revision!==revision) return null;
    return page;
  } catch {return null;}
}

/** Prepared projected envelope; current browser packets still require their original binding. */
export function engineSignalsReply(request:Request,options:EngineAsyncReadOptions) {
  return engineDisplayReplyAsync(request,'signals',projectEngineSignals,{...options,
    admit:context=>engineSignalsRequest(context) ? null : 400});
}
