import {publicSignalSnapshots} from './signalMetrics.ts';
import {bestPickOptions,bestPicks} from './bestPicks.ts';
import type {Sport} from './types';

export type ForecastCursor={offset:number;revision:string;total_count:number;player?:string};

/** Bounded pages, stable snapshot revision, explicit coverage; never silently complete. */
export async function fetchForecasts(sport:Sport,signal?:AbortSignal,view='library',fetchImpl=fetch,maximum=1000,cursor?:ForecastCursor,includeAlternatives=false,player='') {
  if(player!==player.trim() || player!==player.normalize('NFC') || (player!=='' && !/^[\p{L}\p{M}.'\u2019 -]{1,80}$/u.test(player))
    || (player!=='' && view!=='library')) throw new Error('Invalid player search');
  if(!Number.isSafeInteger(maximum) || maximum<1 || maximum>1000 || (cursor &&
    (view!=='library' || (cursor.player ?? '')!==player || !Number.isSafeInteger(cursor.offset) || cursor.offset<1 || cursor.offset>=maximum
      || !Number.isSafeInteger(cursor.total_count) || cursor.total_count>50000 || cursor.total_count<=cursor.offset
      || !/^[a-f0-9]{64}$/.test(cursor.revision)))) throw new Error('Invalid forecast cursor');
  let offset=cursor?.offset ?? 0,revision:string|undefined=cursor?.revision,total=cursor?.total_count ?? 0,complete=false,invalid=0;
  const signals:ReturnType<typeof publicSignalSnapshots>['signals']=[];
  const games=new Map<string,ReturnType<typeof publicSignalSnapshots>['games'][number]>();
  let generated_at:string|null=null;
  // Search the bounded archive on the server, then read at most 1,000 matching rows.
  while(offset<maximum) {
    const params=new URLSearchParams({sport,view,offset:String(offset),limit:String(Math.min(100,maximum-offset))});
    if(revision) params.set('revision',revision);
    if(player) params.set('player',player);
    let response:Response;
    try {response=await fetchImpl('/api/signals?'+params,{cache:'no-store',signal});}
    catch(error) {
      // Only retain already verified research pages; cancellation and malformed data still fail.
      if(view==='library' && revision && signals.length && (error as Error)?.name!=='AbortError') break;
      throw error;
    }
    if(!response.ok) {
      if(view==='library' && revision && signals.length && [409,429,500,502,503,504].includes(response.status)) break;
      throw new Error('Forecasts unavailable');
    }
    const body=await response.json();
    if((body.search_player ?? '')!==player) throw new Error('Invalid player search response');
    if(!Array.isArray(body.signals) || !Array.isArray(body.games) || body.games.length>100
      || !Number.isSafeInteger(body.invalid_signals ?? 0) || (body.invalid_signals ?? 0)<0
      || (body.invalid_signals ?? 0)>5000) throw new Error('Invalid forecast response');
    const empty=body.generated_at===null && body.signals.length===0 && body.games.length===0;
    const page=publicSignalSnapshots(empty ? [] : [{...body,games:[]}],Date.now(),sport);
    if(player && page.signals.some(row=>!row.player.toLowerCase().includes(player.toLowerCase()))) throw new Error('Invalid searched forecast');
    const pagination=body.pagination;
    if(view==='qualified' && pagination===undefined) throw new Error('Invalid forecast coverage');
    if(pagination===undefined && (offset || revision)) throw new Error('Invalid forecast coverage');
    if(pagination!==undefined && (!Number.isSafeInteger(body.total_count) || body.total_count<0 || body.total_count>50000
      || pagination.offset!==offset || !/^[a-f0-9]{64}$/.test(pagination.revision)
      || (revision && (revision!==pagination.revision || total!==body.total_count)) || typeof pagination.complete!=='boolean'
      || (view==='library' && page.signals.length>100))) throw new Error('Invalid forecast coverage');
    signals.push(...page.signals);invalid+=page.invalid_signals+(body.invalid_signals ?? 0);
    for(let index=0;index<body.games.length;index+=10) {
      const batch=publicSignalSnapshots([{...body,signals:[],games:body.games.slice(index,index+10)}],Date.now(),sport);
      for(const game of batch.games) games.set(game.sport+':'+game.game_id,game);
    }
    generated_at ??=page.generated_at;
    // Rolling propagation may still serve the original, strictly validated deployment contract.
    if(pagination===undefined) {total=signals.length;complete=true;break;}
    total=body.total_count;revision=pagination.revision;complete=pagination.complete;
    if(view!=='library') break;
    const next=pagination.next_offset;
    if(complete) {if(next!==null) throw new Error('Invalid forecast coverage');break;}
    if(!Number.isSafeInteger(next) || next<=offset || next>offset+100 || next>total) throw new Error('Invalid forecast cursor');
    offset=next;
  }
  if(view==='qualified' && invalid>0) complete=false;
  return {search_player:player,signals:view==='qualified' ? (complete ? (includeAlternatives ? bestPickOptions(signals) : bestPicks(signals)) : []) : signals,
    games:[...games.values()],game:null,generated_at,invalid_signals:invalid,total_count:total,complete,revision,
    cursor:view==='library' && !complete && revision && offset<total ? {offset,revision,total_count:total,...(player ? {player} : {})} : null};
}
