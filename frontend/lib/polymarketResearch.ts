import {BoundedReadCache} from './boundedReadCache.ts';
import type {Sport} from './types.ts';

const ORIGIN='https://gamma-api.polymarket.com';
const cache=new BoundedReadCache<ResearchResult>({maxEntries:32,maxBytes:4*1024*1024,
  maxEntryBytes:512*1024,maxPending:6});
const SLUG=/^(?:nfl|nba|cfb)-[a-z0-9-]{1,120}$/;

type Fetcher=typeof fetch;
type Row=Record<string,unknown>;
export type ResearchEvent={slug:string;title:string;starts_at:string};
export type ResearchMarket={question:string;outcome:string;best_bid:number|null;best_ask:number|null;
  liquidity_usd:number|null;accepting_orders:boolean};
export type ResearchListing={sport:Sport;source:'Polymarket';observed_at:string;
  scope:string;events:ResearchEvent[]};
export type ResearchDetail={sport:Sport;source:'Polymarket';observed_at:string;
  event:{slug:string;title:string;starts_at:string;url:string};markets:ResearchMarket[]};
type ResearchResult=ResearchListing|ResearchDetail;

function object(value:unknown):Row {
  if(value===null || typeof value!=='object' || Array.isArray(value)) throw new Error('Invalid provider data');
  return value as Row;
}
function text(value:unknown,max=180):string {
  if(typeof value!=='string' || !value.trim() || value.length>max) throw new Error('Invalid provider text');
  return value.trim();
}
function timestamp(value:unknown):string {
  const result=text(value,40);
  if(!/(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(result) || !Number.isFinite(Date.parse(result))) {
    throw new Error('Invalid provider time');
  }
  return new Date(result).toISOString();
}
function price(value:unknown):number|null {
  if((typeof value!=='string' && typeof value!=='number') || value==='') return null;
  const number=Number(value);
  return Number.isFinite(number) && number>=0 && number<=1 ? number : null;
}
function amount(value:unknown):number|null {
  if((typeof value!=='string' && typeof value!=='number') || value==='') return null;
  const number=Number(value);
  return Number.isFinite(number) && number>=0 && number<=1_000_000_000 ? number : null;
}
function firstOutcome(value:unknown):string {
  if(typeof value!=='string' || value.length>256) throw new Error('Invalid outcomes');
  const labels:unknown=JSON.parse(value);
  if(!Array.isArray(labels) || labels.length!==2) throw new Error('Invalid outcomes');
  const first=text(labels[0],80),second=text(labels[1],80);
  if(first===second) throw new Error('Invalid outcomes');
  return first;
}
async function providerJson(path:string,fetcher:Fetcher,maxBytes:number):Promise<unknown> {
  const url=new URL(path,ORIGIN);
  if(url.origin!==ORIGIN) throw new Error('Invalid provider path');
  const response=await fetcher(url,{headers:{'User-Agent':'LineworkResearch/1.0',
    'Accept':'application/json'},redirect:'error',cache:'no-store',signal:AbortSignal.timeout(8000)});
  if(!response.ok || Number(response.headers.get('content-length'))>maxBytes || !response.body
    || !response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
    throw new Error('Provider unavailable');
  }
  const reader=response.body.getReader();
  const decoder=new TextDecoder();
  let bytes=0, body='', complete=false;
  try {
    while(true) {
      const {done,value}=await reader.read();
      if(done) break;
      bytes+=value.byteLength;
      if(bytes>maxBytes) throw new Error('Provider response too large');
      body+=decoder.decode(value,{stream:true});
    }
    body+=decoder.decode();
    complete=true;
  } finally {
    if(!complete) await reader.cancel().catch(()=>{});
    reader.releaseLock();
  }
  return JSON.parse(body) as unknown;
}
function leagueSeries(value:unknown,sport:Sport):string {
  if(!Array.isArray(value) || value.length>1000) throw new Error('Invalid sports metadata');
  const matches=value.map(object).filter(item=>item.sport===sport);
  if(matches.length!==1 || typeof matches[0].series!=='string'
    || !/^[1-9][0-9]{0,9}$/.test(matches[0].series)) throw new Error('League series unavailable');
  return matches[0].series;
}
function seriesEvents(value:unknown,sport:Sport,now:number):ResearchEvent[] {
  const root=object(value);
  if(!Array.isArray(root.events) || root.events.length>100) throw new Error('Invalid series events');
  const events:ResearchEvent[]=[];
  for(const item of root.events) {
    try {
      const event=object(item),slug=text(event.slug,124),starts_at=timestamp(event.startTime);
      if(!SLUG.test(slug) || !slug.startsWith(sport+'-') || event.closed!==false
        || event.active!==true || Date.parse(starts_at)<now-300_000) continue;
      events.push({slug,title:text(event.title),starts_at});
    } catch { /* Omit malformed provider events. */ }
  }
  return events.sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at)).slice(0,20);
}
function detail(value:unknown,selected:ResearchEvent,sport:Sport,observed_at:string):ResearchDetail {
  const root=object(value);
  if(root.slug!==selected.slug || root.closed!==false || root.active!==true
    || !Array.isArray(root.markets) || root.markets.length>100) throw new Error('Event unavailable');
  const markets:ResearchMarket[]=[];
  for(const value of root.markets) {
    try {
      const market=object(value);
      if(market.closed!==false || market.active!==true) continue;
      const accepting_orders=market.acceptingOrders===true;
      const best_bid=accepting_orders ? price(market.bestBid) : null;
      const best_ask=accepting_orders ? price(market.bestAsk) : null;
      if(best_bid!==null && best_ask!==null && best_bid>best_ask) continue;
      markets.push({question:text(market.question,220),outcome:firstOutcome(market.outcomes),best_bid,best_ask,
        liquidity_usd:amount(market.liquidityNum ?? market.liquidity),
        accepting_orders});
    } catch { /* Omit malformed contracts without inventing prices. */ }
  }
  return {sport,source:'Polymarket',observed_at,
    event:{slug:selected.slug,title:selected.title,starts_at:selected.starts_at,
      url:'https://polymarket.com/event/'+selected.slug},markets:markets.slice(0,60)};
}
export async function listPredictionMarkets(sport:Sport,fetcher:Fetcher=fetch,now=Date.now()):Promise<ResearchListing> {
  if(!['nfl','nba','cfb'].includes(sport)) throw new Error('Invalid league');
  const sports=await providerJson('/sports',fetcher,512*1024);
  const series=leagueSeries(sports,sport);
  const data=await providerJson('/series/'+series,fetcher,1024*1024);
  return {sport,source:'Polymarket',observed_at:new Date(now).toISOString(),
    scope:'A bounded sample from the current league series; coverage is not exhaustive.',
    events:seriesEvents(data,sport,now)};
}
export async function predictionMarketDetail(sport:Sport,slug:string,fetcher:Fetcher=fetch,now=Date.now()):Promise<ResearchDetail> {
  if(!SLUG.test(slug) || !slug.startsWith(sport+'-')) throw new Error('Invalid event');
  const listing=await listPredictionMarkets(sport,fetcher,now);
  const selected=listing.events.find(event=>event.slug===slug);
  if(!selected) throw new Error('Event unavailable');
  const data=await providerJson('/events/slug/'+slug,fetcher,1536*1024);
  return detail(data,selected,sport,new Date(now).toISOString());
}
export function cachedPredictionMarkets(sport:Sport,slug?:string):Promise<ResearchResult> {
  if(!slug) return cache.read(sport,60_000,()=>listPredictionMarkets(sport));
  if(!SLUG.test(slug) || !slug.startsWith(sport+'-')) return Promise.reject(new Error('Invalid event'));
  return cache.read(sport+':'+slug,30_000,async()=>{
    const listing=await cache.read(sport,60_000,()=>listPredictionMarkets(sport));
    if(!('events' in listing)) throw new Error('League listing unavailable');
    const selected=listing.events.find(event=>event.slug===slug);
    if(!selected) throw new Error('Event unavailable');
    const data=await providerJson('/events/slug/'+slug,fetch,1536*1024);
    return detail(data,selected,sport,new Date().toISOString());
  });
}