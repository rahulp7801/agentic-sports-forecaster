import {BoundedReadCache} from './boundedReadCache.ts';
import type {Sport} from './types.ts';

const ORIGIN='https://external-api.kalshi.com';
const SERIES:Record<Sport,string>={nfl:'KXNFLGAME',nba:'KXNBAGAME',cfb:'KXNCAAFGAME'};
const cache=new BoundedReadCache<KalshiResearch>({maxEntries:6,maxBytes:4*1024*1024,
  maxEntryBytes:512*1024,maxPending:3});
type Fetcher=typeof fetch;
type Row=Record<string,unknown>;
export type KalshiContract={ticker:string;title:string;url:string;
  yes_bid:number|null;yes_ask:number|null;yes_ask_size:number|null};
export type KalshiEvent={ticker:string;title:string;starts_at:string;markets:KalshiContract[]};
export type KalshiResearch={sport:Sport;source:'Kalshi';observed_at:string;
  scope:string;events:KalshiEvent[]};

function object(value:unknown):Row {
  if(value===null || typeof value!=='object' || Array.isArray(value)) throw new Error('Invalid provider data');
  return value as Row;
}
function label(value:unknown,max=180):string {
  if(typeof value!=='string' || !value.trim() || value.length>max) throw new Error('Invalid provider text');
  return value.trim();
}
function time(value:unknown):string {
  const valueText=label(value,40);
  if(!/(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(valueText) || !Number.isFinite(Date.parse(valueText))) {
    throw new Error('Invalid provider time');
  }
  return new Date(valueText).toISOString();
}
function decimal(value:unknown,max=1):number|null {
  if((typeof value!=='string' && typeof value!=='number') || value==='') return null;
  const number=Number(value);
  return Number.isFinite(number) && number>0 && number<=max ? number : null;
}
async function providerJson(path:string,fetcher:Fetcher):Promise<unknown> {
  const url=new URL(path,ORIGIN);
  if(url.origin!==ORIGIN) throw new Error('Invalid provider path');
  const response=await fetcher(url,{headers:{'Accept':'application/json'},
    redirect:'error',cache:'no-store',signal:AbortSignal.timeout(8000)});
  const maxBytes=1200*1024;
  if(!response.ok || Number(response.headers.get('content-length'))>maxBytes || !response.body
    || !response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
    throw new Error('Provider unavailable');
  }
  const reader=response.body.getReader(),decoder=new TextDecoder();
  let body='',bytes=0,complete=false;
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
function contract(value:unknown,eventTicker:string):KalshiContract|null {
  const item=object(value);
  const ticker=label(item.ticker,120);
  if(item.status!=='active' || item.event_ticker!==eventTicker
    || !ticker.startsWith(eventTicker+'-') || !/^[A-Z0-9-]+$/.test(ticker)) return null;
  const bidSize=decimal(item.yes_bid_size_fp,1_000_000_000);
  const askSize=decimal(item.yes_ask_size_fp,1_000_000_000);
  const yes_bid=bidSize===null ? null : decimal(item.yes_bid_dollars);
  const yes_ask=askSize===null ? null : decimal(item.yes_ask_dollars);
  if(yes_bid!==null && yes_ask!==null && yes_bid>yes_ask) return null;
  return {ticker,title:label(item.title,180),yes_bid,yes_ask,yes_ask_size:yes_ask===null ? null : askSize,
    url:'https://kalshi.com/markets_by_ticker/'+ticker};
}
export async function listKalshiResearch(sport:Sport,fetcher:Fetcher=fetch,now=Date.now()):Promise<KalshiResearch> {
  const series=SERIES[sport];
  if(!series) throw new Error('Invalid league');
  const data=object(await providerJson('/trade-api/v2/events?series_ticker='+series+
    '&status=open&with_nested_markets=true&limit=100',fetcher));
  if(!Array.isArray(data.events) || data.events.length>100
    || typeof data.cursor!=='string' || data.cursor.length>1024) throw new Error('Invalid events');
  const events:KalshiEvent[]=[];
  for(const raw of data.events) {
    try {
      const event=object(raw),ticker=label(event.event_ticker,100);
      if(event.series_ticker!==series || !ticker.startsWith(series+'-')
        || !/^[A-Z0-9-]+$/.test(ticker) || !Array.isArray(event.markets)
        || event.markets.length>10) continue;
      const markets=event.markets.map(value=>{
        try{return contract(value,ticker);}catch{return null;}
      }).filter((value):value is KalshiContract=>value!==null);
      if(!markets.length) continue;
      const starts_at=time(object(event.markets.find(value=>
        value && typeof value==='object' && !Array.isArray(value)
        && (value as Row).ticker===markets[0].ticker)).occurrence_datetime);
      if(Date.parse(starts_at)<now-300_000) continue;
      events.push({ticker,title:label(event.title),starts_at,markets:markets.slice(0,6)});
    } catch { /* Skip malformed event without inventing a quote. */ }
  }
  events.sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at));
  const partial=Boolean(data.cursor) || events.length>20;
  return {sport,source:'Kalshi',observed_at:new Date(now).toISOString(),
    scope:partial
      ? 'A bounded sample of open game events; additional events may be omitted.'
      : 'Open game events returned by the current series query.',
    events:events.slice(0,20)};
}
export function cachedKalshiResearch(sport:Sport):Promise<KalshiResearch> {
  if(!SERIES[sport]) return Promise.reject(new Error('Invalid league'));
  return cache.read(sport,60_000,()=>listKalshiResearch(sport));
}