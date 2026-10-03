export const NO_STORE_HEADERS = {'Cache-Control':'no-store','CDN-Cache-Control':'no-store','Vercel-CDN-Cache-Control':'no-store'} as const;

// Public responses are identical for every visitor. Keep browsers honest about
// freshness while letting Vercel absorb repeat reads before they reach Supabase.
export const PUBLIC_CACHE_HEADERS = {
  live: {
    'Cache-Control': 'no-store',
    'Vercel-CDN-Cache-Control': 'public, s-maxage=30, stale-while-revalidate=30',
  },
  status: {
    'Cache-Control': 'no-store',
    'Vercel-CDN-Cache-Control': 'public, s-maxage=60, stale-while-revalidate=60',
  },
  research: {
    'Cache-Control': 'no-store',
    'Vercel-CDN-Cache-Control': 'public, s-maxage=300, stale-while-revalidate=300',
  },
  archive: {
    'Cache-Control': 'no-store',
    'Vercel-CDN-Cache-Control': 'public, s-maxage=900, stale-while-revalidate=3600',
  },
} as const;

/** Bound edge freshness and stale revalidation to the earliest live eligibility deadline. */
export function liveCacheHeadersUntil(deadlines:readonly number[],now=Date.now()) {
  if(!deadlines.length) return PUBLIC_CACHE_HEADERS.live;
  if(!Number.isFinite(now) || deadlines.some(deadline=>!Number.isFinite(deadline))) return NO_STORE_HEADERS;
  // One second covers integer-second rounding; the extra second covers response transit.
  const remaining=Math.floor((Math.min(...deadlines)-now)/1000)-2;
  if(remaining<1) return NO_STORE_HEADERS;
  const fresh=Math.min(30,remaining),stale=Math.min(30,remaining-fresh);
  return {'Cache-Control':'no-store',
    'Vercel-CDN-Cache-Control':`public, s-maxage=${fresh}${stale>0 ? `, stale-while-revalidate=${stale}` : ''}`};
}

/** Slate state changes at the pick lock and again when the game starts. */
export function slateCacheHeadersUntil(games:readonly {game_time:string}[],now=Date.now()) {
  if(!Number.isFinite(now)) return NO_STORE_HEADERS;
  const starts=games.map(game=>Date.parse(game.game_time));
  if(starts.some(start=>!Number.isFinite(start))) return NO_STORE_HEADERS;
  const deadlines=starts.filter(start=>start>now).map(start=>
    start-60*60000>now ? start-60*60000 : start);
  return deadlines.length ? liveCacheHeadersUntil(deadlines,now) : PUBLIC_CACHE_HEADERS.status;
}

/** Live player history can gain newly ingested games; fixed past cutoffs replay a recorded forecast. */
export function gameLogCacheHeaders(observedBefore:string|null,now=Date.now()) {
  if(observedBefore===null) return PUBLIC_CACHE_HEADERS.research;
  const cutoff=Date.parse(observedBefore);
  return Number.isFinite(now) && Number.isFinite(cutoff) && cutoff<=now
    ? PUBLIC_CACHE_HEADERS.archive : PUBLIC_CACHE_HEADERS.research;
}

export function signalCacheHeaders(view: string) {
  return view === 'qualified' ? PUBLIC_CACHE_HEADERS.live : PUBLIC_CACHE_HEADERS.research;
}
