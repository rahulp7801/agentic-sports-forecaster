import {readImmutableForecastReceipt,type ImmutableForecastReceipt} from './immutableForecastReceipt.ts';
import {historyCutoff} from './forecastHistory.ts';
import {gameLogQuery} from './gameLogQuery.ts';
import {validPlayerId} from './publicGameLogs.ts';
import type {AvailabilityEvidence,Direction,EVSignal,PropType,Sport} from './types';

export const IMMUTABLE_FORECAST_QUERY=`SELECT id,scan_id,payload,payload_sha256,
  to_char(recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS recorded_at
FROM analytics.predictions
WHERE id=$1 AND payload_sha256=$2 AND recorded_at IS NOT NULL
  AND payload_sha256=encode(sha256(convert_to(payload,'UTF8')),'hex')
LIMIT 1`;

export type ImmutableForecastContext={id:string;game_id:string;sport:Sport;player:string;player_id:string;
  prop_type:PropType;line:number;direction:Direction;snapped_at:string;captured_at:string;game_start_time:string;
  model_version:string;forecast_cutoff:string;history_policy_version?:string;history_observed_before?:string;
  availability?:Pick<AvailabilityEvidence,'status'|'roster_confirmed'|'captured_at'|'team'>};
export type ImmutableForecastRead=(sql:string,args:readonly unknown[])=>Promise<unknown[]>;
export type ImmutableForecastResolution={status:'resolved';receipt:Omit<ImmutableForecastReceipt,'payload'>;
  context:ImmutableForecastContext;query:ReturnType<typeof gameLogQuery>}
  |{status:'unavailable';reason:'invalid_request'|'prediction_unavailable'|'receipt_unavailable'|'history_context_unavailable'|'chronology_unavailable'};

const hash=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
function object(value:unknown):value is Record<string,unknown> {
  try {
    return Boolean(value)&&typeof value==='object'&&!Array.isArray(value)
      &&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null)
      &&!Object.getOwnPropertySymbols(value).length
      &&Object.values(Object.getOwnPropertyDescriptors(value)).every(item=>item.enumerable&&Object.hasOwn(item,'value'));
  } catch {return false;}
}
function text(value:unknown,maximum:number):string {
  if(typeof value!=='string'||!value.trim()||value.length>maximum||/[\u0000-\u001f]/.test(value)) throw Error('Unavailable');
  return value;
}

/** Retained ISO instants are compared at microsecond precision, never through a pg Date. */
function instant(value:unknown):bigint {
  const raw=text(value,64);
  const match=/^(\d{4}-\d{2}-\d{2})T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?:\.(\d{1,6}))?(Z|[+-](?:0\d|1[0-4]):[0-5]\d)$/.exec(raw);
  if(!match||match[1]<'0001-01-01'||/[+-]14:(?!00$)/.test(raw)) throw Error('Unavailable');
  const day=new Date(match[1]+'T00:00:00Z');
  if(!Number.isFinite(day.valueOf())||day.toISOString().slice(0,10)!==match[1]) throw Error('Unavailable');
  const milliseconds=Date.parse(`${match[1]}T${match[2]}:${match[3]}:${match[4]}Z`);
  const zone=match[6],offset=zone==='Z' ? 0 : (Number(zone.slice(1,3))*60+Number(zone.slice(4,6)))*(zone[0]==='+' ? 1 : -1);
  return BigInt(milliseconds)*BigInt(1000)+BigInt((match[5] ?? '').padEnd(6,'0'))-BigInt(offset)*BigInt(60_000_000);
}

/** Match the retained version policy without the legacy helper's millisecond comparisons. */
function sourcePolicy(retained:ImmutableForecastContext):string|null {
  return retained.sport==='nba'&&retained.model_version==='empirical-jeffreys-v4-nba-source-asof-v1' ? 'nba-source-asof-v1'
    : retained.sport==='nfl'&&retained.model_version==='empirical-jeffreys-v4-nfl-history-v1' ? 'nfl-explicit-receiving-v1'
      : retained.sport==='cfb'&&retained.model_version==='empirical-jeffreys-v4-cfb-history-v1' ? 'cfb-explicit-receiving-v1' : null;
}

function context(receipt:ImmutableForecastReceipt):ImmutableForecastContext {
  const raw=receipt.payload;
  if(typeof raw.sport!=='string'||!['nba','nfl','cfb'].includes(raw.sport)) throw Error('Unavailable');
  const sport=raw.sport as Sport;
  const props=sport==='nba' ? ['points','rebounds','assists','threes','pra','steals','blocks']
    : sport==='cfb' ? ['pass_yds','rush_yds','rec_yds','receptions'] : ['pass_yds','pass_tds','rush_yds','rec_yds','receptions'];
  if(!validPlayerId(raw.player_id,sport)||typeof raw.prop_type!=='string'||!props.includes(raw.prop_type)
    ||typeof raw.line!=='number'||!Number.isFinite(raw.line)||raw.line<0||raw.line>10000
    ||(raw.direction!=='over'&&raw.direction!=='under')) throw Error('Unavailable');
  const result:ImmutableForecastContext={id:receipt.id,game_id:text(raw.game_id,128),sport,player:text(raw.player,100),player_id:raw.player_id,
    prop_type:raw.prop_type as PropType,line:raw.line,direction:raw.direction,snapped_at:text(raw.quote_time,64),
    captured_at:text(raw.captured_at,64),game_start_time:text(raw.game_start_time,64),model_version:text(raw.model_version,64),
    forecast_cutoff:text(raw.forecast_cutoff,10)};
  for(const key of ['history_policy_version','history_observed_before'] as const) if(raw[key]!==undefined) result[key]=text(raw[key],64);
  if(raw.availability!==undefined) {
    if(!object(raw.availability)||typeof raw.availability.status!=='string'||!['observed','unavailable'].includes(raw.availability.status)
      ||typeof raw.availability.roster_confirmed!=='boolean') throw Error('Unavailable');
    const availability:NonNullable<ImmutableForecastContext['availability']>={status:raw.availability.status as AvailabilityEvidence['status'],
      roster_confirmed:raw.availability.roster_confirmed};
    if(availability.status==='observed') {
      if(!availability.roster_confirmed) throw Error('Unavailable');
      availability.captured_at=text(raw.availability.captured_at,64);availability.team=text(raw.availability.team,5);
    } else if(availability.roster_confirmed) throw Error('Unavailable');
    result.availability=availability;
  }
  return result;
}

/** Private lookup preparation only. No frontend credentials, live route or caller-selected history scope. */
export async function resolveImmutableForecast(request:unknown,predictionRead:ImmutableForecastRead,now=Date.now()):Promise<ImmutableForecastResolution> {
  const unavailable=(reason:Extract<ImmutableForecastResolution,{status:'unavailable'}>['reason']):ImmutableForecastResolution=>({status:'unavailable',reason});
  let id:string,payload_sha256:string;
  try {
    if(!object(request)||Object.keys(request).length!==2) return unavailable('invalid_request');
    const descriptors=Object.getOwnPropertyDescriptors(request);
    const requestedId:unknown=descriptors.id?.value,requestedHash:unknown=descriptors.payload_sha256?.value;
    if(!hash(requestedId)||!hash(requestedHash)||!Number.isSafeInteger(now)||now<0||now>253402300799999
      ||typeof predictionRead!=='function') return unavailable('invalid_request');
    id=requestedId;payload_sha256=requestedHash;
  } catch {return unavailable('invalid_request');}
  let rows:unknown[];
  try {rows=await predictionRead(IMMUTABLE_FORECAST_QUERY,[id,payload_sha256]);}
  catch {return unavailable('prediction_unavailable');}
  let receipt:ImmutableForecastReceipt|null;
  try {
    if(!Array.isArray(rows)||rows.length!==1) return unavailable('prediction_unavailable');
    receipt=readImmutableForecastReceipt(rows[0],{id,payload_sha256});
  } catch {return unavailable('receipt_unavailable');}
  if(!receipt) return unavailable('receipt_unavailable');
  let retained:ImmutableForecastContext,before:string,observed:string;
  try {
    retained=context(receipt);
    // Cast only the retained history subset for compatibility with unchanged helpers;
    // no omitted probability, price, stake or presentation fields are fabricated.
    before=historyCutoff(retained as EVSignal);
    const policy=sourcePolicy(retained);
    if(policy&&retained.history_policy_version!==policy) throw Error('Unavailable');
    observed=policy ? text(retained.history_observed_before,64) : retained.captured_at;
  } catch {return unavailable('history_context_unavailable');}
  try {
    const quote=instant(retained.snapped_at),generated=instant(receipt.payload.model_generated_at),capture=instant(retained.captured_at),
      recorded=instant(receipt.recorded_at),start=instant(retained.game_start_time),selection=instant(observed);
    // Keep the existing one-minute future-clock tolerance; comparisons between
    // retained source instants themselves never lose their microseconds.
    const latestClock=(BigInt(now)+BigInt(60_000))*BigInt(1000)+BigInt(999);
    if(quote>generated||generated>capture||capture>recorded||recorded>=start||recorded>latestClock
      ||quote>selection||selection>capture) return unavailable('chronology_unavailable');
    if(sourcePolicy(retained)&&selection>generated) return unavailable('chronology_unavailable');
    if(retained.availability?.status==='observed'&&instant(retained.availability.captured_at)>capture)
      return unavailable('chronology_unavailable');
  } catch {return unavailable('chronology_unavailable');}
  const stat=retained.sport==='nfl'&&(retained.prop_type==='pass_yds'||retained.prop_type==='rush_yds') ? retained.prop_type : undefined;
  const query=gameLogQuery({sport:retained.sport,player:'',playerId:retained.player_id,exact:true,limit:20,before,observedBefore:observed,
    ...(stat ? {stat} : {})});
  return {status:'resolved',receipt:{id:receipt.id,scan_id:receipt.scan_id,payload_sha256:receipt.payload_sha256,recorded_at:receipt.recorded_at},
    context:retained,query};
}
