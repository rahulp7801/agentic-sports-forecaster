import {reportGameLogValidationFailure} from '@/lib/databaseFailure';
import { databaseQuery } from '@/lib/database';
import { gameLogRequest,publicGameLogs } from '@/lib/publicGameLogs';
import { NextResponse } from 'next/server';
import {NO_STORE_HEADERS,gameLogCacheHeaders} from '@/lib/publicCache';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  let query:ReturnType<typeof gameLogRequest>;
  try {query=gameLogRequest(new URL(request.url).searchParams);} catch {
    return NextResponse.json({error:'Invalid game-log request'}, {status:400,headers:NO_STORE_HEADERS});
  }
  const {sport,player,limit,before,exact,playerId,observedBefore}=query;
  let validatingRows=false;
  try {
    const filters=' WHERE sport=$1 '
      + 'AND ($6::text IS NULL OR player_id=$6) '
      + 'AND ($6::text IS NOT NULL OR $2=\'\' OR CASE WHEN $5 THEN lower(player_name)=lower($2) ELSE strpos(lower(player_name),lower($2))>0 END) '
      + 'AND ($4::date IS NULL OR game_date<$4::date) '
      + 'AND ($7::timestamptz IS NULL OR record_available_at<=$7::timestamptz) ';
    const sql=(sport==='cfb' || sport==='nfl') && observedBefore!==null
      ? 'SELECT payload FROM ('
        + 'SELECT DISTINCT ON (sport,COALESCE(player_id,player_name),game_key) '
        + 'payload,game_date,player_name,game_key FROM dashboard_gamelog_versions'
        + filters
        + 'ORDER BY sport,COALESCE(player_id,player_name),game_key,record_available_at DESC NULLS LAST'
        + ') versions ORDER BY game_date DESC,player_name,game_key LIMIT $3'
      : 'SELECT payload FROM dashboard_gamelogs_asof'+filters
        + 'ORDER BY game_date DESC,player_name,game_key LIMIT $3';
    const {rows} = await databaseQuery<{payload: unknown}>(sql,
      [sport,player,limit,before,exact,playerId ?? null,observedBefore],'gamelogs');
    validatingRows=true;
    return NextResponse.json({logs:publicGameLogs(rows.map(row=>row.payload),sport)},
      {headers:gameLogCacheHeaders(observedBefore)});
  } catch {
    if(validatingRows) reportGameLogValidationFailure();
    return NextResponse.json({error:'Game logs are temporarily unavailable.',logs:[]}, {status:503,headers:NO_STORE_HEADERS});
  }
}
