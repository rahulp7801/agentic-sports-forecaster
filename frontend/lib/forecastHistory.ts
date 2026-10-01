import type {EVSignal} from './types';
import {publicGameLogs,validPlayerId,observationCutoff} from './publicGameLogs.ts';

/** Descriptive outcomes at this line, never a betting replay or a new forecast. */
export function historyCutoff(signal:EVSignal) {
  const cutoff=signal.forecast_cutoff;
  if(!cutoff || !/^\d{4}-\d{2}-\d{2}$/.test(cutoff) || Number(cutoff.slice(0,4))<1 || !Number.isFinite(Date.parse(cutoff))
    || new Date(`${cutoff}T00:00:00Z`).toISOString().slice(0,10)!==cutoff) throw new Error('Forecast cutoff unavailable');
  if(!/([zZ]|[+-]\d\d:\d\d)$/.test(signal.snapped_at) || !Number.isFinite(Date.parse(signal.snapped_at))) throw new Error('Price capture time unavailable');
  // Date-only logs cannot establish completion across overnight league games.
  const captureDay=new Date(Date.parse(signal.snapped_at)-86_400_000).toISOString().slice(0,10);
  return captureDay<cutoff ? captureDay : cutoff;
}

/** Only display rows the source had recorded before this forecast was captured. */
export function historyObservedBefore(signal:EVSignal) {
  historyCutoff(signal);
  const captured=signal.captured_at;
  if(!captured) throw new Error('Forecast capture time unavailable');
  observationCutoff(captured);
  if(Date.parse(captured)<Date.parse(signal.snapped_at)
      || !signal.game_start_time || !observationCutoff(signal.game_start_time)
      || Date.parse(captured)>=Date.parse(signal.game_start_time)) {
    throw new Error('Forecast capture time unavailable');
  }
  return captured;
}

export function forecastHistory(value:unknown,signal:EVSignal,count=20) {
  if(!Number.isSafeInteger(count) || count<1 || count>200) throw new Error('Invalid history window');
  const cutoff=historyCutoff(signal);
  if(signal.player_id!==undefined && !validPlayerId(signal.player_id,signal.sport)) throw new Error('Invalid forecast identity');
  const validated=publicGameLogs(value,signal.sport);
  if(!signal.player_id && validated.some(row=>row.player_id!==undefined
    && String(row.player).toLowerCase()===signal.player.toLowerCase())) throw new Error('Stable forecast identity unavailable');
  const logs=validated
    .filter(row=>(signal.player_id ? row.player_id===signal.player_id : String(row.player).toLowerCase()===signal.player.toLowerCase()) && String(row.date)<cutoff)
    .sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,count);
  let wins=0,losses=0,ties=0,missing=0,sum=0;
  const seen=new Set<string>();
  const rows=logs.map(row=>{
    const key=`${row.date}:${row.team}:${row.opponent}`;
    if(seen.has(key)) throw new Error('Duplicate historical game');
    seen.add(key);
    const keys=signal.prop_type==='pra' ? ['points','rebounds','assists'] : [signal.prop_type];
    const values=keys.map(key=>row[key]);
    const stat=values.every(v=>typeof v==='number' && Number.isFinite(v)) ? (values as number[]).reduce((a,b)=>a+b,0) : null;
    let outcome='Missing stat';
    if(stat===null) missing++;
    else {
      sum+=stat;
      if(stat===signal.line) {ties++;outcome='Tie';}
      else if((stat>signal.line)===(signal.direction==='over')) {wins++;outcome='Matched direction';}
      else {losses++;outcome='Opposite direction';}
    }
    return {date:String(row.date),team:String(row.team),opponent:String(row.opponent),stat,outcome};
  });
  return {rows,wins,losses,ties,missing,decided:wins+losses,rate:wins+losses ? wins/(wins+losses) : null,
    mean:logs.length-missing ? sum/(logs.length-missing) : null};
}

function summarize(rows:ReturnType<typeof forecastHistory>['rows']) {
    const known=rows.filter(row=>row.stat!==null);
    const decided=known.filter(row=>row.outcome!=='Tie');
    const wins=decided.filter(row=>row.outcome==='Matched direction').length;
    return {games:rows.length,observed:known.length,missing:rows.length-known.length,
      mean:known.length ? known.reduce((sum,row)=>sum+row.stat!,0)/known.length : null,
      wins,decided:decided.length,rate:decided.length ? wins/decided.length : null,
      newest:rows[0]?.date ?? null,oldest:rows.at(-1)?.date ?? null,
      teams:[...new Set(rows.map(row=>row.team))]};
}

/** Disjoint recent windows preserve missing observations instead of replacing them. */
export function recentForm(value:unknown,signal:EVSignal) {
  const history=forecastHistory(value,signal,20);
  const recent=summarize(history.rows.slice(0,5));
  const previous=summarize(history.rows.slice(5,10));
  const daysBeforeForecast=recent.newest
    ? Math.floor((Date.parse(signal.forecast_cutoff!)-Date.parse(recent.newest))/86400000) : null;
  return {recent,previous,daysBeforeForecast,
    meanChange:recent.mean!==null && previous.mean!==null ? recent.mean-previous.mean : null};
}

/** Calendar recency is separate from a last-N window that may span old teams. */
export function calendarForm(value:unknown,signal:EVSignal) {
  const history=forecastHistory(value,signal,20);
  const before=historyCutoff(signal);
  const from=new Date(Date.parse(signal.forecast_cutoff!)-30*86400000).toISOString().slice(0,10);
  const rows=history.rows.filter(row=>row.date>=from);
  const availability=signal.availability;
  const team=availability?.status==='observed' && availability.roster_confirmed
    && typeof availability.team==='string' && availability.team.trim() ? availability.team : null;
  return {from,before,allTeams:summarize(rows),capturedTeam:team,
    capturedTeamSample:team ? summarize(rows.filter(row=>row.team===team)) : null,
    limitedToLatest20:history.rows.length===20 && history.rows.at(-1)!.date>=from};
}
