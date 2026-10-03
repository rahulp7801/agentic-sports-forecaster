import type {Direction,PropType,Sport} from './types';

export const FORECAST_HISTORY_DISPLAY_PROTOCOL='linework-forecast-history-display-v1';
export type ForecastHistoryDisplaySubject={forecast_id:string;forecast_record_sha256:string;
  sport:Sport;player:string;player_id:string|null;prop_type:PropType;line:number;direction:Direction};
export type ForecastHistoryDisplayScope={captured_at:string|null;game_date_before:string|null;
  source_observed_before:string|null;source_cutoff_kind:'model_selection'|'forecast_capture'|'unavailable'};
export type ForecastHistoryDisplayAvailableScope={captured_at:string;game_date_before:string;
  source_observed_before:string;source_cutoff_kind:'model_selection'|'forecast_capture'};
export type ForecastHistoryDisplayBinding={revision:string;subject:ForecastHistoryDisplaySubject;scope:ForecastHistoryDisplayScope};
export type ForecastHistoryDisplayRow={date:string;team:string;opponent:string;stat:number|null;
  outcome:'Missing stat'|'Tie'|'Matched direction'|'Opposite direction'};
export type ForecastHistoryDisplayWindow={rows:ForecastHistoryDisplayRow[];wins:number;losses:number;
  ties:number;missing:number;decided:number;rate:number|null;mean:number|null};
export type ForecastHistoryDisplaySummary={games:number;observed:number;missing:number;mean:number|null;
  wins:number;decided:number;rate:number|null;newest:string|null;newestObserved:string|null;oldest:string|null;teams:string[]};
export type ForecastHistoryDisplayRecent={recent:ForecastHistoryDisplaySummary;previous:ForecastHistoryDisplaySummary;
  daysBeforeForecast:number|null;observedDaysBeforeForecast:number|null;meanChange:number|null};
export type ForecastHistoryDisplayCalendar={from:string;before:string;allTeams:ForecastHistoryDisplaySummary;
  capturedTeam:string|null;capturedTeamSample:ForecastHistoryDisplaySummary|null;limitedToLatest20:boolean};
export type ForecastHistoryDisplayContextLabel={player:string;team:string;relationship:'teammate'|'opponent';
  unit:'offense'|'defense';window:string[];recent:string};
type Common=ForecastHistoryDisplayBinding&{protocol:typeof FORECAST_HISTORY_DISPLAY_PROTOCOL;producer_version:string};
export type ForecastHistoryDisplay=(Common&{status:'available';scope:ForecastHistoryDisplayAvailableScope;source_coverage:'bounded_as_of_records';
  windows:{'10':ForecastHistoryDisplayWindow;'20':ForecastHistoryDisplayWindow};recent:ForecastHistoryDisplayRecent;
  calendar:ForecastHistoryDisplayCalendar;card_summary:string;context_labels:ForecastHistoryDisplayContextLabel[]})
  |(Common&{status:'unavailable';reason:string});

type ObjectValue=Record<string,unknown>;
function invalid():never {throw Error('Invalid forecast history display');}
function object(value:unknown):ObjectValue {
  if(!value||typeof value!=='object'||Array.isArray(value)) return invalid();
  const prototype=Object.getPrototypeOf(value),descriptors=Object.getOwnPropertyDescriptors(value);
  if(prototype!==null&&prototype!==Object.prototype||Object.getOwnPropertySymbols(value).length
    ||Object.keys(descriptors).length>64||Object.values(descriptors).some(item=>!item.enumerable||!Object.hasOwn(item,'value'))) return invalid();
  return value as ObjectValue;
}
function text(value:unknown,maximum:number):string {
  return typeof value==='string'&&value.length>0&&value.length<=maximum&&Boolean(value.trim())
    &&!/[\u0000-\u001f]/.test(value) ? value : invalid();
}
function number(value:unknown,minimum:number,maximum:number):number {
  return typeof value==='number'&&Number.isFinite(value)&&value>=minimum&&value<=maximum ? value : invalid();
}
function integer(value:unknown,maximum:number):number {
  const result=number(value,0,maximum);return Number.isSafeInteger(result) ? result : invalid();
}
function nullableNumber(value:unknown,minimum:number,maximum:number):number|null {
  return value===null ? null : number(value,minimum,maximum);
}
function enumeration<T extends string>(value:unknown,values:readonly T[]):T {
  return typeof value==='string'&&values.includes(value as T) ? value as T : invalid();
}
function day(value:unknown):string {
  const result=text(value,10),parsed=new Date(result+'T00:00:00Z');
  return /^\d{4}-\d{2}-\d{2}$/.test(result)&&result>='0001-01-01'&&Number.isFinite(parsed.valueOf())
    &&parsed.toISOString().slice(0,10)===result ? result : invalid();
}
function timestamp(value:unknown):string {
  const result=text(value,64);
  if(!/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1[0-4]):[0-5]\d)$/.test(result)
    ||/[+-]14:(?!00$)/.test(result)||!Number.isFinite(Date.parse(result))) return invalid();
  day(result.slice(0,10));return result;
}
function nullableDay(value:unknown):string|null {return value===null ? null : day(value);}
function nullableTimestamp(value:unknown):string|null {return value===null ? null : timestamp(value);}
function digest(value:unknown):string {
  const result=text(value,64);return /^[a-f0-9]{64}$/.test(result) ? result : invalid();
}
function array<T>(value:unknown,maximum:number,read:(item:unknown)=>T):T[] {
  if(!Array.isArray(value)||Object.getPrototypeOf(value)!==Array.prototype||value.length>maximum
    ||Object.getOwnPropertySymbols(value).length||Object.keys(value).length!==value.length
    ||Object.keys(value).some((key,index)=>key!==String(index))
    ||Object.entries(Object.getOwnPropertyDescriptors(value)).some(([key,item])=>key!=='length'
      &&(!item.enumerable||!Object.hasOwn(item,'value')))) return invalid();
  return value.map(read);
}
function subject(value:unknown):ForecastHistoryDisplaySubject {
  const source=object(value);
  return {forecast_id:text(source.forecast_id,128),forecast_record_sha256:digest(source.forecast_record_sha256),
    sport:enumeration(source.sport,['nba','nfl','cfb']),player:text(source.player,100),
    player_id:source.player_id===null ? null : text(source.player_id,20),
    prop_type:enumeration(source.prop_type,['points','rebounds','assists','threes','pra','steals','blocks',
      'pass_yds','pass_tds','rush_yds','rec_yds','receptions']),line:number(source.line,0,10000),
    direction:enumeration(source.direction,['over','under'])};
}
function scope(value:unknown):ForecastHistoryDisplayScope {
  const source=object(value),captured_at=nullableTimestamp(source.captured_at),source_observed_before=nullableTimestamp(source.source_observed_before);
  if(captured_at!==null&&source_observed_before!==null&&Date.parse(source_observed_before)>Date.parse(captured_at)) return invalid();
  return {captured_at,game_date_before:nullableDay(source.game_date_before),source_observed_before,
    source_cutoff_kind:enumeration(source.source_cutoff_kind,['model_selection','forecast_capture','unavailable'])};
}
function binding(value:unknown):ForecastHistoryDisplayBinding {
  const source=object(value);return {revision:digest(source.revision),subject:subject(source.subject),scope:scope(source.scope)};
}
function before(value:unknown,cutoff:string):string|null {
  const result=nullableDay(value);return result===null||result<cutoff ? result : invalid();
}
function row(value:unknown,cutoff:string):ForecastHistoryDisplayRow {
  const source=object(value),date=day(source.date),stat=nullableNumber(source.stat,-30000,30000);
  const outcome=enumeration(source.outcome,['Missing stat','Tie','Matched direction','Opposite direction']);
  if(date>=cutoff||(stat===null)!==(outcome==='Missing stat')) return invalid();
  return {date,team:text(source.team,20),opponent:text(source.opponent,20),stat,outcome};
}
function window(value:unknown,maximum:number,cutoff:string):ForecastHistoryDisplayWindow {
  const source=object(value),rows=array(source.rows,maximum,item=>row(item,cutoff)),seen=new Set<string>();
  const labels={'Matched direction':0,'Opposite direction':0,'Tie':0,'Missing stat':0};
  for(let index=0;index<rows.length;index++) {
    const item=rows[index],key=JSON.stringify([item.date,item.team,item.opponent]);
    if(seen.has(key)||(index>0&&item.date>rows[index-1].date)) return invalid();seen.add(key);labels[item.outcome]++;
  }
  const result={rows,wins:integer(source.wins,maximum),losses:integer(source.losses,maximum),
    ties:integer(source.ties,maximum),missing:integer(source.missing,maximum),decided:integer(source.decided,maximum),
    rate:nullableNumber(source.rate,0,1),mean:nullableNumber(source.mean,-30000,30000)};
  if(result.wins+result.losses+result.ties+result.missing!==rows.length||result.decided!==result.wins+result.losses
    ||(result.decided===0)!==(result.rate===null)||(rows.length-result.missing===0)!==(result.mean===null)
    ||result.wins!==labels['Matched direction']||result.losses!==labels['Opposite direction']
    ||result.ties!==labels.Tie||result.missing!==labels['Missing stat']) return invalid();
  return result;
}
function summary(value:unknown,maximum:number,cutoff:string):ForecastHistoryDisplaySummary {
  const source=object(value),newest=before(source.newest,cutoff),newestObserved=before(source.newestObserved,cutoff),oldest=before(source.oldest,cutoff);
  if(newest!==null&&oldest!==null&&oldest>newest||newestObserved!==null&&newest!==null&&newestObserved>newest) return invalid();
  const result={games:integer(source.games,maximum),observed:integer(source.observed,maximum),missing:integer(source.missing,maximum),
    mean:nullableNumber(source.mean,-30000,30000),wins:integer(source.wins,maximum),decided:integer(source.decided,maximum),
    rate:nullableNumber(source.rate,0,1),newest,newestObserved,oldest,teams:array(source.teams,maximum,item=>text(item,20))};
  if(result.observed+result.missing!==result.games||result.wins>result.decided||result.decided>result.observed
    ||(result.decided===0)!==(result.rate===null)||(result.observed===0)!==(result.mean===null)
    ||(result.games===0)!==(newest===null)||(result.games===0)!==(oldest===null)
    ||(result.observed===0)!==(newestObserved===null)||(result.games===0)!==(result.teams.length===0)
    ||result.teams.length>result.games||new Set(result.teams).size!==result.teams.length
    ||newestObserved!==null&&oldest!==null&&newestObserved<oldest) return invalid();
  return result;
}
function recent(value:unknown,cutoff:string):ForecastHistoryDisplayRecent {
  const source=object(value);
  const age=(value:unknown)=>value===null ? null : integer(value,4000000);
  const result={recent:summary(source.recent,5,cutoff),previous:summary(source.previous,5,cutoff),
    daysBeforeForecast:age(source.daysBeforeForecast),observedDaysBeforeForecast:age(source.observedDaysBeforeForecast),
    meanChange:nullableNumber(source.meanChange,-60000,60000)};
  if((result.recent.newest===null)!==(result.daysBeforeForecast===null)
    ||(result.recent.newestObserved===null)!==(result.observedDaysBeforeForecast===null)
    ||(result.recent.mean===null||result.previous.mean===null)!==(result.meanChange===null)) return invalid();
  return result;
}
function calendar(value:unknown,cutoff:string):ForecastHistoryDisplayCalendar {
  const source=object(value),from=day(source.from),end=day(source.before);
  const capturedTeam=source.capturedTeam===null ? null : text(source.capturedTeam,5);
  if(from>=end||end!==cutoff||typeof source.limitedToLatest20!=='boolean'
    ||(capturedTeam===null)!==(source.capturedTeamSample===null)) return invalid();
  return {from,before:end,allTeams:summary(source.allTeams,20,cutoff),capturedTeam,
    capturedTeamSample:source.capturedTeamSample===null ? null : summary(source.capturedTeamSample,20,cutoff),
    limitedToLatest20:source.limitedToLatest20};
}
function contextLabel(value:unknown):ForecastHistoryDisplayContextLabel {
  const source=object(value);
  return {player:text(source.player,100),team:text(source.team,5),relationship:enumeration(source.relationship,['teammate','opponent']),
    unit:enumeration(source.unit,['offense','defense']),window:array(source.window,3,item=>text(item,1000)),recent:text(source.recent,3000)};
}

/** Read descriptive outputs for the exact expected record and source scope; never infer a model or decision. */
export function readForecastHistoryDisplay(value:unknown,expected:ForecastHistoryDisplayBinding):ForecastHistoryDisplay|null {
  try {
    const source=object(value),actual=binding(source),wanted=binding(expected);
    if(source.protocol!==FORECAST_HISTORY_DISPLAY_PROTOCOL||JSON.stringify(actual)!==JSON.stringify(wanted)) return null;
    const common:Common={protocol:FORECAST_HISTORY_DISPLAY_PROTOCOL,producer_version:text(source.producer_version,64),...actual};
    if(source.status==='unavailable') return {...common,status:'unavailable',reason:text(source.reason,300)};
    if(source.status!=='available'||source.source_coverage!=='bounded_as_of_records'||actual.scope.captured_at===null
      ||actual.scope.game_date_before===null||actual.scope.source_observed_before===null||actual.scope.source_cutoff_kind==='unavailable') return null;
    const cutoff=actual.scope.game_date_before,windows=object(source.windows);
    const ten=window(windows['10'],10,cutoff),twenty=window(windows['20'],20,cutoff);
    if(ten.rows.length>twenty.rows.length||ten.rows.some((item,index)=>JSON.stringify(item)!==JSON.stringify(twenty.rows[index]))) return null;
    return {...common,scope:{captured_at:actual.scope.captured_at,game_date_before:cutoff,
      source_observed_before:actual.scope.source_observed_before,source_cutoff_kind:actual.scope.source_cutoff_kind},
      status:'available',source_coverage:'bounded_as_of_records',windows:{'10':ten,'20':twenty},
      recent:recent(source.recent,cutoff),calendar:calendar(source.calendar,cutoff),card_summary:text(source.card_summary,2000),
      context_labels:array(source.context_labels,8,contextLabel)};
  } catch {return null;}
}
