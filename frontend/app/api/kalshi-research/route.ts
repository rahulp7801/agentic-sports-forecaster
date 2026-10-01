import {cachedKalshiResearch} from '../../../lib/kalshiResearch.ts';
import {NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS} from '../../../lib/publicCache.ts';

export const dynamic='force-dynamic';

export async function GET(request:Request) {
  const sport=new URL(request.url).searchParams.get('sport');
  if(sport!=='nfl' && sport!=='nba' && sport!=='cfb') {
    return Response.json({error:'Invalid league.'},{status:400,headers:NO_STORE_HEADERS});
  }
  try {
    return Response.json(await cachedKalshiResearch(sport),{headers:PUBLIC_CACHE_HEADERS.status});
  } catch {
    return Response.json({error:'Kalshi research is temporarily unavailable.'},
      {status:503,headers:NO_STORE_HEADERS});
  }
}