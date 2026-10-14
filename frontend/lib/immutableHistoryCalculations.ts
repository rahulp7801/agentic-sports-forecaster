import type {ImmutableForecastContext} from './immutableForecastHistory.ts';
import {publicGameLogs,validPlayerId} from './publicGameLogs.ts';

const NFL_STAT_TEAM_ALIASES:Record<string,string>={LAR:'LA',WSH:'WAS'};
const NBA_STAT_TEAM_ALIASES:Record<string,string>={
  GS:'GSW',NO:'NOP',NY:'NYK',SA:'SAS',UTAH:'UTA',WSH:'WAS',
};

/** Private descriptive calculations; source and chronology admission precede this call. */
function forecastHistory(value:unknown,context:ImmutableForecastContext,count=20) {
  if(!Number.isSafeInteger(count) || count<1 || count>200) throw new Error('Invalid history window');
  const cutoff=context.forecast_cutoff;
  if(!validPlayerId(context.player_id,context.sport)) throw new Error('Invalid forecast identity');
  const validated=publicGameLogs(value,context.sport);
  const logs=validated
    .filter(row=>row.player_id===context.player_id && String(row.date)<cutoff)
    .sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,count);
  let wins=0,losses=0,ties=0,missing=0,sum=0;
  const seen=new Set<string>();
  const rows=logs.map(row=>{
    const key=`${row.date}:${row.team}:${row.opponent}`;
    if(seen.has(key)) throw new Error('Duplicate historical game');
    seen.add(key);
    const keys=context.prop_type==='pra' ? ['points','rebounds','assists'] : [context.prop_type];
    const values=keys.map(key=>row[key]);
    const stat=values.every(v=>typeof v==='number' && Number.isFinite(v)) ? (values as number[]).reduce((a,b)=>a+b,0) : null;
    let outcome='Missing stat';
    if(stat===null) missing++;
    else {
      sum+=stat;
      if(stat===context.line) {ties++;outcome='Tie';}
      else if((stat>context.line)===(context.direction==='over')) {wins++;outcome='Matched direction';}
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
      newest:rows[0]?.date ?? null,newestObserved:known[0]?.date ?? null,
      oldest:rows.at(-1)?.date ?? null,
      teams:[...new Set(rows.map(row=>row.team))]};
}

function sameCapturedTeam(sport:ImmutableForecastContext['sport'],left:string,right:string) {
  const statTeam=(team:string)=>sport==='nfl' ? NFL_STAT_TEAM_ALIASES[team] ?? team
    : sport==='nba' ? NBA_STAT_TEAM_ALIASES[team] ?? team : team;
  return statTeam(left)===statTeam(right);
}

function recentForm(value:unknown,context:ImmutableForecastContext) {
  const history=forecastHistory(value,context,20);
  const recent=summarize(history.rows.slice(0,5));
  const previous=summarize(history.rows.slice(5,10));
  const daysBeforeForecast=recent.newest
    ? Math.floor((Date.parse(context.forecast_cutoff)-Date.parse(recent.newest))/86400000) : null;
  const observedDaysBeforeForecast=recent.newestObserved
    ? Math.floor((Date.parse(context.forecast_cutoff)-Date.parse(recent.newestObserved))/86400000) : null;
  return {recent,previous,daysBeforeForecast,observedDaysBeforeForecast,
    meanChange:recent.mean!==null && previous.mean!==null ? recent.mean-previous.mean : null};
}

function calendarForm(value:unknown,context:ImmutableForecastContext) {
  const history=forecastHistory(value,context,20);
  const before=context.forecast_cutoff;
  const from=new Date(Date.parse(context.forecast_cutoff)-30*86400000).toISOString().slice(0,10);
  const rows=history.rows.filter(row=>row.date>=from);
  // The immutable resolver already compared availability and forecast instants
  // at retained precision. Do not repeat that check through Date.parse here.
  const availability=context.availability;
  const team=availability?.status==='observed' && availability.roster_confirmed
    && typeof availability.team==='string' && availability.team.trim() ? availability.team : null;
  return {from,before,allTeams:summarize(rows),capturedTeam:team,
    capturedTeamSample:team ? summarize(rows.filter(row=>sameCapturedTeam(context.sport,row.team,team))) : null,
    limitedToLatest20:history.rows.length===20 && history.rows.at(-1)!.date>=from};
}

function pickCardFormSummary(logs:unknown,context:ImmutableForecastContext) {
  const form=calendarForm(logs,context);
  const team=form.capturedTeam;
  const sample=form.capturedTeamSample;
  if(!team || !sample) return 'Current-team form was not verified at forecast capture.';
  const limit=form.limitedToLatest20 ? ' Only the latest 20 records were checked.' : '';
  if(!sample.games) return `No ${team} game appears in the retrieved records from the prior 30 days.${limit}`;
  if(!sample.newestObserved) return `${sample.games} ${team} game${sample.games===1?'':'s'} recorded in the prior 30 days; this stat was unavailable. Latest recorded game ${sample.newest}; no observed stat in these records. This does not establish current form.${limit}`;
  const daysBeforeStat=Math.round((Date.parse(form.before)-Date.parse(sample.newestObserved))/86400000);
  const latest=`Latest observed stat ${sample.newestObserved}, ${daysBeforeStat} day${daysBeforeStat===1?'':'s'} before the target game.`;
  const missingLatest=sample.newest!==sample.newestObserved
    ? ` Newer recorded game ${sample.newest} has no observed value for this stat.` : '';
  const stale=daysBeforeStat>14 ? ' This does not establish current form.' : '';
  return `${team} last 30 days: ${sample.observed} recorded stat${sample.observed===1?'':'s'} in ${sample.games} game${sample.games===1?'':'s'}, average ${sample.mean!.toFixed(1)} (line ${context.line}). ${latest}${missingLatest}${stale}${limit}`;
}

/** Consume only an immutable resolved subject and its bounded source records. */
export function immutableHistoryCalculations(logs:unknown,context:ImmutableForecastContext) {
  return {windows:{'10':forecastHistory(logs,context,10),'20':forecastHistory(logs,context,20)},
    recent:recentForm(logs,context),calendar:calendarForm(logs,context),card_summary:pickCardFormSummary(logs,context)};
}
