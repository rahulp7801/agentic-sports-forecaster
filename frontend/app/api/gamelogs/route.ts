import {requireOwner} from '../../../lib/ownerAccess.ts';
import {reportGameLogValidationFailure} from '@/lib/databaseFailure';
import { databaseQuery } from '@/lib/database';
import { gameLogRequest,publicGameLogs } from '@/lib/publicGameLogs';
import {gameLogQuery} from '@/lib/gameLogQuery';
import {nflCoreHistoryPayloads} from '@/lib/nflCoreHistoryEvidence';
import { NextResponse } from 'next/server';
import {NO_STORE_HEADERS,gameLogCacheHeaders} from '@/lib/publicCache';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const denied=await requireOwner(request); if(denied) return denied;
  let query:ReturnType<typeof gameLogRequest>;
  try {query=gameLogRequest(new URL(request.url).searchParams);} catch {
    return NextResponse.json({error:'Invalid game-log request'}, {status:400,headers:NO_STORE_HEADERS});
  }
  const {sport,observedBefore}=query;
  let validatingRows=false;
  try {
    const {sql,args}=gameLogQuery(query);
    const {rows} = await databaseQuery<{payload: unknown;source_row?: unknown}>(sql,args,'gamelogs');
    validatingRows=true;
    const payloads=query.stat===undefined ? rows.map(row=>row.payload) : nflCoreHistoryPayloads(rows,query.playerId ?? '');
    return NextResponse.json({logs:publicGameLogs(payloads,sport)},
      {headers:gameLogCacheHeaders(observedBefore)});
  } catch {
    if(validatingRows) reportGameLogValidationFailure();
    return NextResponse.json({error:'Game logs are temporarily unavailable.',logs:[]}, {status:503,headers:NO_STORE_HEADERS});
  }
}
