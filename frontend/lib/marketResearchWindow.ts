import {liveCacheHeadersUntil,NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS} from './publicCache.ts';

/** A retained provider snapshot is never an open-game quote after event start. */
export function upcomingMarketEvents<T extends {starts_at:string}>(events:readonly T[],now=Date.now()):T[] {
  return events.filter(event=>Number.isFinite(Date.parse(event.starts_at)) && Date.parse(event.starts_at)>now);
}

export function marketResearchCacheHeaders(events:readonly {starts_at:string}[],now=Date.now()) {
  if(!Number.isFinite(now)) return NO_STORE_HEADERS;
  const starts=events.map(event=>Date.parse(event.starts_at));
  if(starts.some(start=>!Number.isFinite(start))) return NO_STORE_HEADERS;
  const upcoming=starts.filter(start=>start>now);
  return upcoming.length ? liveCacheHeadersUntil(upcoming,now) : PUBLIC_CACHE_HEADERS.status;
}
