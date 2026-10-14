import {requireOwner} from '../../../lib/ownerAccess.ts';
import {publicPickBoard} from '../../../lib/pickBoard.ts';
import {NO_STORE_HEADERS,liveCacheHeadersUntil} from '../../../lib/publicCache.ts';
import type {Sport} from '../../../lib/types.ts';

export const dynamic='force-dynamic';

export async function GET(request:Request) {
  const denied=await requireOwner(request); if(denied) return denied;
  const sport=new URL(request.url).searchParams.get('sport');
  if(!['nfl','nba','cfb'].includes(String(sport))) return Response.json({error:'Unsupported sport.'},
    {status:400,headers:NO_STORE_HEADERS});
  try {
    const {snapshots}=await import('@/lib/database');
    const keys=[`picks:${sport}`,`player-profiles:${sport}`];
    const data=await snapshots(keys);
    const now=Date.now(),board=publicPickBoard(data[keys[0]],data[keys[1]],sport as Sport,now);
    return Response.json(board,{headers:liveCacheHeadersUntil(
      board.current.map(pick=>Date.parse(pick.game_start_time ?? '')),now)});
  } catch {
    return Response.json({error:'The pregame pick board is temporarily unavailable.'},{status:503,headers:NO_STORE_HEADERS});
  }
}
