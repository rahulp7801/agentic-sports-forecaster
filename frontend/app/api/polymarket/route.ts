import {requireOwner} from '../../../lib/ownerAccess.ts';
import {cachedPredictionMarkets,MarketEventStartedError} from '../../../lib/polymarketResearch.ts';
import {marketResearchCacheHeaders,upcomingMarketEvents} from '../../../lib/marketResearchWindow.ts';
import {NO_STORE_HEADERS} from '../../../lib/publicCache.ts';
import type {Sport} from '../../../lib/types.ts';

export const dynamic='force-dynamic';

export async function GET(request:Request) {
  const denied=await requireOwner(request); if(denied) return denied;
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
    const result=await cachedPredictionMarkets(sport as Sport,event ?? undefined),now=Date.now();
    if('events' in result) {
      const events=upcomingMarketEvents(result.events,now);
      return Response.json({...result,events},{headers:marketResearchCacheHeaders(events,now)});
    }
    if(Date.parse(result.event.starts_at)<=now) return Response.json({error:'Event already started.'},
      {status:410,headers:NO_STORE_HEADERS});
    return Response.json(result,{headers:marketResearchCacheHeaders([result.event],now)});
  } catch(error) {
    if(error instanceof MarketEventStartedError) return Response.json({error:'Event already started.'},
      {status:410,headers:NO_STORE_HEADERS});
    return Response.json({error:'Prediction market research is temporarily unavailable.'},
      {status:503,headers:NO_STORE_HEADERS});
  }
}
