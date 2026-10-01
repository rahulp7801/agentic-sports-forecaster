import {cachedPredictionMarkets} from '../../../lib/polymarketResearch.ts';
import {NO_STORE_HEADERS,PUBLIC_CACHE_HEADERS} from '../../../lib/publicCache.ts';
import type {Sport} from '../../../lib/types.ts';

export const dynamic='force-dynamic';

export async function GET(request:Request) {
  const params=new URL(request.url).searchParams;
  const sport=params.get('sport');
  const event=params.get('event');
  if(sport!=='nfl' && sport!=='nba' && sport!=='cfb') {
    return Response.json({error:'Invalid league.'},{status:400,headers:NO_STORE_HEADERS});
  }
  if(event!==null && !new RegExp('^'+sport+'-[a-z0-9-]{1,120}$').test(event)) {
    return Response.json({error:'Invalid event.'},{status:400,headers:NO_STORE_HEADERS});
  }
  try {
    const result=await cachedPredictionMarkets(sport as Sport,event ?? undefined);
    return Response.json(result,{headers:event ? PUBLIC_CACHE_HEADERS.live : PUBLIC_CACHE_HEADERS.status});
  } catch {
    return Response.json({error:'Prediction market research is temporarily unavailable.'},
      {status:503,headers:NO_STORE_HEADERS});
  }
}