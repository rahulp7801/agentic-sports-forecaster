export const NO_STORE_HEADERS = {'Cache-Control':'no-store','CDN-Cache-Control':'no-store','Vercel-CDN-Cache-Control':'no-store'} as const;
// Compatibility names for the dashboard routes. Owner data must never enter a shared cache.
// The bounded server snapshot cache remains available behind authenticated handlers.
export const PUBLIC_CACHE_HEADERS={live:NO_STORE_HEADERS,status:NO_STORE_HEADERS,research:NO_STORE_HEADERS,archive:NO_STORE_HEADERS} as const;
export function liveCacheHeadersUntil(_deadlines:readonly number[],_now=Date.now()) {void _deadlines;void _now;return NO_STORE_HEADERS;}
export function slateCacheHeadersUntil(_games:readonly {game_time:string}[],_now=Date.now()) {void _games;void _now;return NO_STORE_HEADERS;}
export function gameLogCacheHeaders(_observedBefore:string|null,_now=Date.now()) {void _observedBefore;void _now;return NO_STORE_HEADERS;}
export function signalCacheHeaders(_view:string) {void _view;return NO_STORE_HEADERS;}
